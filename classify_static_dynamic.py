import csv
import requests
from bs4 import BeautifulSoup
import re
import time
import os # Ajout du module os

# Définition des indicateurs connus (listes non exhaustives)
DYNAMIC_URL_EXTENSIONS = ('.php', '.asp', '.aspx', '.jsp', '.py', '.rb', '.cgi')
# Mots-clés pour les balises <meta name="generator"> indiquant un CMS (dynamique)
CMS_GENERATORS_KEYWORDS = ['wordpress', 'joomla', 'drupal', 'typo3', 'wix', 'squarespace', 'shopify', 'magento', 'prestashop', 'modx']
# Mots-clés pour les en-têtes X-Powered-By indiquant une technologie dynamique
DYNAMIC_POWERED_BY_KEYWORDS = ['php', 'asp.net', 'express', 'ruby', 'python', 'java', 'node.js', 'coldfusion']
# Mots-clés pour les balises <meta name="generator"> indiquant un générateur de site statique (SSG)
SSG_GENERATORS_KEYWORDS = ['jekyll', 'hugo', 'gatsby', 'eleventy', 'vuepress', 'mkdocs', 'pelican', 'gridsome', 'astro']
# Attention : Next.js peut être statique (SSG) ou dynamique (SSR/ISR).

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
        response = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
        response.raise_for_status()

        powered_by = response.headers.get('X-Powered-By', '').lower()
        if any(tech_keyword in powered_by for tech_keyword in DYNAMIC_POWERED_BY_KEYWORDS):
            return 'dynamic'

        final_url = response.url.lower()
        if any(final_url.endswith(ext) for ext in DYNAMIC_URL_EXTENSIONS):
            return 'dynamic'
        
        if 'Set-Cookie' in response.headers:
            cookies_header = response.headers['Set-Cookie'].lower()
            if any(s_cookie_name in cookies_header for s_cookie_name in ['phpsessid', 'jsessionid', 'asp.net_sessionid', 'sessionid', 'connect.sid']):
                 return 'dynamic'

        content_type = response.headers.get('Content-Type', '').lower()
        if 'text/html' in content_type:
            soup = BeautifulSoup(response.content, 'html.parser')
            html_lower = str(soup).lower()

            generator_meta = soup.find('meta', attrs={'name': re.compile(r'^generator$', re.I)})
            if generator_meta and generator_meta.get('content'):
                generator_content = generator_meta.get('content', '').lower()
                if any(cms_keyword in generator_content for cms_keyword in CMS_GENERATORS_KEYWORDS):
                    return 'dynamic'
                if any(ssg_keyword in generator_content for ssg_keyword in SSG_GENERATORS_KEYWORDS):
                    if 'next.js' not in generator_content:
                         return 'static'

            if 'wp-content/' in html_lower or 'wp-includes/' in html_lower or '/wp-json/' in html_lower:
                return 'dynamic'
            if 'sites/default/files' in html_lower or 'misc/drupal.js' in html_lower:
                return 'dynamic'
            if 'components/com_content' in html_lower or '/media/jui/js/' in html_lower:
                 return 'dynamic'

            forms = soup.find_all('form')
            for form in forms:
                action = form.get('action', '').lower()
                method = form.get('method', '').lower()
                if method == 'post' and action:
                    if any(action.endswith(ext) for ext in DYNAMIC_URL_EXTENSIONS):
                        return 'dynamic'
                    # if not action.startswith(('http', '#', 'javascript:')) and action != '':
                    #     pass # Peut-être trop agressif de classer dynamique ici

        if final_url.endswith(('.html', '.htm')):
            return 'static'

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
            urls_to_process = [row[0].strip() for row in reader if row and row[0].strip()]
            
            total_urls = len(urls_to_process)
            print(f"Nombre total d'URLs à traiter : {total_urls}")

            for i, url in enumerate(urls_to_process):
                print(f"\nTraitement de l'URL {i+1}/{total_urls} : {url}")
                time.sleep(0.75)
                classification_result = classify_website(url)
                
                if classification_result == 'static':
                    static_sites_urls.append([url])
                    print(f" -> Classification : STATIQUE")
                elif classification_result == 'dynamic':
                    dynamic_sites_urls.append([url])
                    print(f" -> Classification : DYNAMIQUE")
                else:
                    error_sites_info.append([url, classification_result])
                    print(f" -> Classification : ERREUR ({classification_result})")

    except FileNotFoundError:
        print(f"ERREUR : Le fichier d'entrée '{input_csv_path}' n'a pas été trouvé.")
        return
    except Exception as e:
        print(f"ERREUR lors de la lecture ou du traitement du CSV d'entrée : {e}")
        return

    try:
        with open(static_csv_path, mode='w', newline='', encoding='utf-8') as outfile_static:
            writer_static = csv.writer(outfile_static)
            writer_static.writerow(['URL'])
            writer_static.writerows(static_sites_urls)
        print(f"\nListe des sites statiques sauvegardée dans : {static_csv_path} ({len(static_sites_urls)} sites)")

        with open(dynamic_csv_path, mode='w', newline='', encoding='utf-8') as outfile_dynamic:
            writer_dynamic = csv.writer(outfile_dynamic)
            writer_dynamic.writerow(['URL'])
            writer_dynamic.writerows(dynamic_sites_urls)
        print(f"Liste des sites dynamiques sauvegardée dans : {dynamic_csv_path} ({len(dynamic_sites_urls)} sites)")

        if error_sites_info:
            with open(error_csv_path, mode='w', newline='', encoding='utf-8') as outfile_error:
                writer_error = csv.writer(outfile_error)
                writer_error.writerow(['URL', 'TypeErreur'])
                writer_error.writerows(error_sites_info)
            print(f"Liste des URLs en erreur sauvegardée dans : {error_csv_path} ({len(error_sites_info)} erreurs)")
        else:
            print("Aucune erreur rencontrée lors du traitement des URLs.")

    except IOError as e:
        print(f"ERREUR lors de l'écriture des fichiers CSV de sortie : {e}")


if __name__ == '__main__':
    # Configurez ici le chemin de votre fichier CSV d'entrée
    fichier_entree = 'input_urls.csv'  # REMPLACEZ par le nom de votre fichier CSV d'entrée

    # --- MODIFICATION POUR LES CHEMINS DE SORTIE ---
    # Obtenir le chemin absolu du fichier d'entrée
    abs_input_path = os.path.abspath(fichier_entree)
    
    # Obtenir le répertoire du fichier d'entrée
    # Si le fichier d'entrée n'existe pas et que le chemin est relatif,
    # cela utilisera le répertoire de travail actuel comme base pour dirname.
    # Si le fichier d'entrée existe, cela prendra le répertoire du fichier.
    # Si le fichier d'entrée est juste un nom (ex: 'input.csv') et est dans le CWD,
    # base_path sera le CWD.
    base_path = os.path.dirname(abs_input_path)
    
    # Si le fichier_entree n'a pas de composant de répertoire (c'est-à-dire qu'il est dans le CWD)
    # os.path.dirname() pour un simple nom de fichier peut retourner une chaîne vide.
    # Dans ce cas, on utilise le CWD explicitement.
    if not base_path: # ou if base_path == os.path.dirname(os.path.basename(abs_input_path))
        base_path = os.getcwd()

    # Construire les chemins complets pour les fichiers de sortie
    fichier_statiques = os.path.join(base_path, 'sites_statiques_resultat.csv')
    fichier_dynamiques = os.path.join(base_path, 'sites_dynamiques_resultat.csv')
    fichier_erreurs = os.path.join(base_path, 'urls_en_erreur_resultat.csv')
    # --- FIN DE LA MODIFICATION POUR LES CHEMINS DE SORTIE ---

    print("Début du script de classification des sites web.")
    print(f"Le fichier d'entrée est : {abs_input_path}")
    print(f"Les fichiers de sortie seront écrits dans le répertoire : {base_path}")
    
    main_process(fichier_entree, fichier_statiques, fichier_dynamiques, fichier_erreurs)
    print("\nScript terminé.")