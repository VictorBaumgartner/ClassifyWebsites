import csv
import requests
from bs4 import BeautifulSoup
import re
import time

# Définition des indicateurs connus (listes non exhaustives)
DYNAMIC_URL_EXTENSIONS = ('.php', '.asp', '.aspx', '.jsp', '.py', '.rb', '.cgi')
# Mots-clés pour les balises <meta name="generator"> indiquant un CMS (dynamique)
CMS_GENERATORS_KEYWORDS = ['wordpress', 'joomla', 'drupal', 'typo3', 'wix', 'squarespace', 'shopify', 'magento', 'prestashop', 'modx']
# Mots-clés pour les en-têtes X-Powered-By indiquant une technologie dynamique
DYNAMIC_POWERED_BY_KEYWORDS = ['php', 'asp.net', 'express', 'ruby', 'python', 'java', 'node.js', 'coldfusion']
# Mots-clés pour les balises <meta name="generator"> indiquant un générateur de site statique (SSG)
SSG_GENERATORS_KEYWORDS = ['jekyll', 'hugo', 'gatsby', 'eleventy', 'vuepress', 'mkdocs', 'pelican', 'gridsome', 'astro']
# Attention : Next.js peut être statique (SSG) ou dynamique (SSR/ISR).
# La présence de 'next.js' dans le generator est un indicateur, mais pas une preuve de staticité.

def classify_website(url):
    """
    Inspecte une URL pour tenter de déterminer si le site est statique ou dynamique.
    Retourne 'static', 'dynamic', ou une chaîne d'erreur (ex: 'error_timeout').
    """
    if not re.match(r'^[a-zA-Z]+://', url): # Ajoute http si aucun schéma n'est présent
        url = 'http://' + url

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36 SiteClassifierBot/1.0'
        }
        # Timeout raisonnable pour la requête
        response = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
        response.raise_for_status() # Lève une exception pour les codes d'erreur HTTP (4xx, 5xx)

        # 1. Vérifier l'en-tête 'X-Powered-By'
        powered_by = response.headers.get('X-Powered-By', '').lower()
        if any(tech_keyword in powered_by for tech_keyword in DYNAMIC_POWERED_BY_KEYWORDS):
            return 'dynamic'

        # 2. Vérifier les extensions d'URL dynamiques courantes
        # Attention : response.url contient l'URL finale après redirections
        final_url = response.url.lower()
        if any(final_url.endswith(ext) for ext in DYNAMIC_URL_EXTENSIONS):
            return 'dynamic'
        
        # 3. Vérifier l'en-tête 'Set-Cookie' (présence de cookies de session)
        # C'est un indicateur, mais les sites statiques peuvent aussi utiliser des cookies via JS.
        if 'Set-Cookie' in response.headers:
            # Rechercher des cookies typiques de session
            cookies_header = response.headers['Set-Cookie'].lower()
            if any(s_cookie_name in cookies_header for s_cookie_name in ['phpsessid', 'jsessionid', 'asp.net_sessionid', 'sessionid', 'connect.sid']):
                 return 'dynamic'


        # 4. Analyser le contenu HTML (si c'en est)
        content_type = response.headers.get('Content-Type', '').lower()
        if 'text/html' in content_type:
            soup = BeautifulSoup(response.content, 'html.parser') # Utiliser response.content pour une meilleure gestion de l'encodage
            html_lower = str(soup).lower() # Contenu HTML en minuscules pour la recherche

            # Vérifier les balises <meta name="generator">
            generator_meta = soup.find('meta', attrs={'name': re.compile(r'^generator$', re.I)})
            if generator_meta and generator_meta.get('content'):
                generator_content = generator_meta.get('content', '').lower()
                if any(cms_keyword in generator_content for cms_keyword in CMS_GENERATORS_KEYWORDS):
                    return 'dynamic'
                if any(ssg_keyword in generator_content for ssg_keyword in SSG_GENERATORS_KEYWORDS):
                    # Si c'est Next.js, il faut être prudent.
                    # Sans analyse plus poussée de __NEXT_DATA__, on peut avoir un faux positif pour statique.
                    # Pour simplifier, si c'est un SSG connu (hors Next.js avec plus de doutes), on penche vers statique.
                    if 'next.js' not in generator_content: # Next.js est plus ambigu
                         return 'static'
                    # Pour Next.js, on laisse d'autres règles potentiellement le classer dynamique, ou il tombera dans le défaut.

            # Vérifier les empreintes de CMS courants (ex: WordPress)
            if 'wp-content/' in html_lower or 'wp-includes/' in html_lower or '/wp-json/' in html_lower:
                return 'dynamic'
            if 'sites/default/files' in html_lower or 'misc/drupal.js' in html_lower: # Drupal
                return 'dynamic'
            if 'components/com_content' in html_lower or '/media/jui/js/' in html_lower: # Joomla
                 return 'dynamic'


            # Vérifier les formulaires pointant vers des scripts dynamiques (heuristique simple)
            forms = soup.find_all('form')
            for form in forms:
                action = form.get('action', '').lower()
                method = form.get('method', '').lower()
                if method == 'post' and action: # Les formulaires POST sont souvent dynamiques
                    if any(action.endswith(ext) for ext in DYNAMIC_URL_EXTENSIONS):
                        return 'dynamic'
                    # Si l'action est une URL relative non vide, cela peut indiquer un traitement dynamique.
                    if not action.startswith(('http', '#', 'javascript:')) and action != '':
                        # Heuristique : un formulaire POST avec une action non triviale suggère dynamique.
                        #return 'dynamic' # Peut être trop agressif.
                        pass


        # 5. Heuristique de repli : si l'URL finale se termine par .html ou .htm
        # ET qu'aucun indicateur dynamique fort n'a été trouvé, considérer comme statique.
        if final_url.endswith(('.html', '.htm')):
            return 'static'

        # 6. Comportement par défaut : si après toutes ces vérifications, aucun signal clair n'est trouvé,
        # on doit faire un choix. Beaucoup de sites modernes sont dynamiques ou ont des aspects dynamiques.
        # Par défaut, on peut pencher vers 'dynamic'.
        return 'dynamic'

    except requests.exceptions.Timeout:
        print(f"Timeout pour l'URL : {url}")
        return 'error_timeout'
    except requests.exceptions.TooManyRedirects:
        print(f"Trop de redirections pour l'URL : {url}")
        return 'error_redirects'
    except requests.exceptions.SSLError:
        print(f"Erreur SSL pour l'URL : {url}")
        return 'error_ssl'
    except requests.exceptions.ConnectionError:
        print(f"Erreur de connexion pour l'URL : {url}")
        return 'error_connection'
    except requests.exceptions.RequestException as e:
        print(f"Erreur de requête pour l'URL {url}: {e}")
        return 'error_request'
    except Exception as e:
        print(f"Erreur inattendue avec l'URL {url}: {e}")
        return 'error_unexpected'


def main_process(input_csv_path, static_csv_path, dynamic_csv_path, error_csv_path):
    """
    Fonction principale pour lire le CSV d'entrée, classifier les URLs et écrire les résultats.
    """
    static_sites_urls = []
    dynamic_sites_urls = []
    error_sites_info = []

    print(f"Lecture du fichier d'entrée : {input_csv_path}")
    try:
        with open(input_csv_path, mode='r', newline='', encoding='utf-8') as infile:
            reader = csv.reader(infile)
            # Optionnel: sauter l'en-tête si votre CSV en a un
            # next(reader, None) 
            
            urls_to_process = [row[0].strip() for row in reader if row and row[0].strip()]
            
            total_urls = len(urls_to_process)
            print(f"Nombre total d'URLs à traiter : {total_urls}")

            for i, url in enumerate(urls_to_process):
                print(f"\nTraitement de l'URL {i+1}/{total_urls} : {url}")
                
                # Petit délai pour être respectueux envers les serveurs
                time.sleep(0.75) # Délai de 0.75 seconde
                
                classification_result = classify_website(url)
                
                if classification_result == 'static':
                    static_sites_urls.append([url])
                    print(f" -> Classification : STATIQUE")
                elif classification_result == 'dynamic':
                    dynamic_sites_urls.append([url])
                    print(f" -> Classification : DYNAMIQUE")
                else: # C'est une erreur
                    error_sites_info.append([url, classification_result])
                    print(f" -> Classification : ERREUR ({classification_result})")

    except FileNotFoundError:
        print(f"ERREUR : Le fichier d'entrée '{input_csv_path}' n'a pas été trouvé.")
        return
    except Exception as e:
        print(f"ERREUR lors de la lecture ou du traitement du CSV d'entrée : {e}")
        return

    # Écriture des résultats dans les fichiers CSV de sortie
    try:
        with open(static_csv_path, mode='w', newline='', encoding='utf-8') as outfile_static:
            writer_static = csv.writer(outfile_static)
            writer_static.writerow(['URL']) # En-tête
            writer_static.writerows(static_sites_urls)
        print(f"\nListe des sites statiques sauvegardée dans : {static_csv_path} ({len(static_sites_urls)} sites)")

        with open(dynamic_csv_path, mode='w', newline='', encoding='utf-8') as outfile_dynamic:
            writer_dynamic = csv.writer(outfile_dynamic)
            writer_dynamic.writerow(['URL']) # En-tête
            writer_dynamic.writerows(dynamic_sites_urls)
        print(f"Liste des sites dynamiques sauvegardée dans : {dynamic_csv_path} ({len(dynamic_sites_urls)} sites)")

        if error_sites_info:
            with open(error_csv_path, mode='w', newline='', encoding='utf-8') as outfile_error:
                writer_error = csv.writer(outfile_error)
                writer_error.writerow(['URL', 'TypeErreur']) # En-tête
                writer_error.writerows(error_sites_info)
            print(f"Liste des URLs en erreur sauvegardée dans : {error_csv_path} ({len(error_sites_info)} erreurs)")
        else:
            print("Aucune erreur rencontrée lors du traitement des URLs.")

    except IOError as e:
        print(f"ERREUR lors de l'écriture des fichiers CSV de sortie : {e}")


if __name__ == '__main__':
    # Configurez ici les chemins de vos fichiers
    # Créez un fichier 'input_urls.csv' avec une URL par ligne dans la première colonne.
    # Par exemple :
    # https://www.example.com
    # http://www.test-site.org/page.html
    # ...
    
    # Exemple de création d'un fichier input_urls.csv pour tester rapidement :
    # urls_de_test = [
    #     "https://www.ville-rochefort.fr/hebre-musee-et-patrimoine-0",
    #     "https://www.nice.fr/fr/culture/musees-et-galeries/musee-massena-le-musee",
    #     "https://www.musee-matisse-nice.org/fr/", # MODX CMS -> dynamic
    #     "https://www.mamac-nice.org/fr/", # Probablement CMS -> dynamic
    #     "https://www.aixenprovence.fr/Musee-du-Pavillon-de-Vendome", # Site de ville -> dynamic
    #     "https://www.aixenprovence.fr/Musee-Arbaud", # Site de ville -> dynamic
    #     "https://www.museeciotaden.org/", # Semble WordPress -> dynamic
    #     "https://www.w3.org/TR/html5/", # Exemple de page .html -> static
    #     "https://github.com/", # Très dynamique
    #     "http://info.cern.ch/" # Historique, simple -> static (mais pourrait être servi dynamiquement)
    # ]
    # with open('input_urls_pour_test.csv', 'w', newline='', encoding='utf-8') as f_test:
    #     writer_test = csv.writer(f_test)
    #     for url_item in urls_de_test:
    #         writer_test.writerow([url_item])
    # print("Fichier 'input_urls_pour_test.csv' créé pour le test.")
    
    fichier_entree = 'input_urls.csv'  # REMPLACEZ par le nom de votre fichier CSV d'entrée
    fichier_statiques = 'sites_statiques_resultat.csv'
    fichier_dynamiques = 'sites_dynamiques_resultat.csv'
    fichier_erreurs = 'urls_en_erreur_resultat.csv'

    print("Début du script de classification des sites web.")
    main_process(fichier_entree, fichier_statiques, fichier_dynamiques, fichier_erreurs)
    print("\nScript terminé.")