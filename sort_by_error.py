import pandas as pd
from pathlib import Path

# Répertoire courant
current_dir = Path.cwd()

# Fichier source
input_file = current_dir / 'urls_en_erreur_resultat.csv'

# Dossier de sortie
output_dir = current_dir / 'links_by_error'
output_dir.mkdir(exist_ok=True)

# Charger le CSV
df = pd.read_csv(input_file)

# Nettoyer les noms de colonnes
df.columns = df.columns.str.strip().str.lower()

# Grouper par type d'erreur et sauvegarder chaque groupe
for error_type, group in df.groupby('typeerreur'):
    output_file = output_dir / f"{error_type}.csv"
    group.drop_duplicates().to_csv(output_file, index=False)

print(f"✅ Fichiers CSV générés dans le dossier : {output_dir}")
