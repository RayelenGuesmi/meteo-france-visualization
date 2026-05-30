import pandas as pd
from sqlalchemy import create_engine, text
import glob
import os

# =============================================================================
# CONFIGURATION DE LA CONNEXION POSTGRESQL
# =============================================================================
# Ces paramètres correspondent au conteneur Docker lancé avec :
# docker run -d --name postgres_meteo -e POSTGRES_DB=meteo
#            -e POSTGRES_USER=meteo_admin -e POSTGRES_PASSWORD=meteo_admin
#            -p 5433:5432 postgres:15
# Le port 5433 est utilisé car le port 5432 était déjà occupé sur la machine.
# =============================================================================
DB_CONFIG = {
    "host": "localhost",
    "port": 5433,          # Port exposé par Docker (5432 interne → 5433 externe)
    "database": "meteo",   # Nom de la base de données créée dans le conteneur
    "user": "meteo_admin",
    "password": "meteo_admin"
}

# Création du moteur SQLAlchemy (interface entre Python et PostgreSQL)
engine = create_engine(
    f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
)


# COLONNES À CONSERVER DEPUIS LES FICHIERS MÉTÉO FRANCE
COLONNES_UTILES = [
    "NUM_STA",    # Identifiant numérique unique de la station météo
    "NOM_USUEL",  # Nom lisible de la station (ex: "PARIS-MONTSOURIS")
    "LAT",        # Latitude de la station en degrés décimaux (WGS84)
    "LON",        # Longitude de la station en degrés décimaux (WGS84)
    "ALTI",       # Altitude de la station en mètres (influence sur les températures)
    "AAAAMMJJ",   # Date de l'observation au format YYYYMMDD → convertie en date Python
    "TN",         # Température minimale du jour en dixièmes de °C (ex: 125 = 12.5°C)
    "TX",         # Température maximale du jour en dixièmes de °C
    "TM",         # Température moyenne du jour en dixièmes de °C
    "RR",         # Cumul des précipitations du jour en dixièmes de mm
    "DG",         # Durée de gel dans la journée en minutes (T° < 0°C)
    "FFM",        # Vitesse moyenne du vent sur 10 min en dixièmes de m/s
]


def charger_fichier(chemin):

    print(f"  Chargement : {os.path.basename(chemin)}")

    # Lecture du CSV compressé — dtype=str pour éviter les erreurs de parsing
    # na_values gère les codes de valeurs manquantes propres à Météo France
    df = pd.read_csv(
        chemin,
        compression='gzip',  # Décompression automatique du .gz
        sep=';',              # Séparateur point-virgule (standard Météo France)
        dtype=str,            # Tout en string d'abord pour éviter les erreurs de type
        na_values=['', 'mq', 'MQ', 'NaN']  # 'mq' = "manquant" dans les fichiers MF
    )

    # On ne garde que les colonnes définies dans COLONNES_UTILES
    # (certaines peuvent être absentes selon le fichier → intersection)
    colonnes_presentes = [c for c in COLONNES_UTILES if c in df.columns]
    df = df[colonnes_presentes]

    # --- Conversion de la date ---
    # Le format Météo France est YYYYMMDD (ex: 20230715 → 15 juillet 2023)
    # On extrait aussi l'année et le mois pour faciliter les agrégations dans Metabase
    if "AAAAMMJJ" in df.columns:
        df["date"] = pd.to_datetime(df["AAAAMMJJ"], format="%Y%m%d", errors="coerce")
        df["annee"] = df["date"].dt.year   # Utile pour les tendances annuelles
        df["mois"] = df["date"].dt.month   # Utile pour les analyses saisonnières
        df.drop(columns=["AAAAMMJJ"], inplace=True)  # Supprime la colonne originale

    # --- Conversion des colonnes numériques ---
    # Les valeurs sont stockées en string avec parfois une virgule comme séparateur
    # décimal → on remplace par un point avant la conversion en float
    for col in ["TN", "TX", "TM", "RR", "DG", "FFM", "LAT", "LON", "ALTI"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].str.replace(",", "."), errors="coerce")

    # --- Normalisation des noms de colonnes ---
    # PostgreSQL est sensible à la casse → on passe tout en minuscules
    # (ex: "NOM_USUEL" → "nom_usuel", "TX" → "tx")
    df.columns = [c.lower() for c in df.columns]

    # --- Suppression des lignes sans date valide ---
    # Une ligne sans date n'est pas exploitable dans Metabase pour les séries temporelles
    if "date" in df.columns:
        df = df.dropna(subset=["date"])

    return df


def main():
    # --- Chargement du fichier nettoyé ---
    # Ce fichier est produit par clean_data.py (doublons supprimés,
    # valeurs aberrantes neutralisées, dates validées)
    fichier_nettoye = "data_nettoyee.csv"

    if not os.path.exists(fichier_nettoye):
        print("Fichier data_nettoyee.csv introuvable.")
        print("   Lance d'abord : python clean_data.py")
        return

    print(f"Chargement de {fichier_nettoye}...")
    df_final = pd.read_csv(fichier_nettoye, parse_dates=["date"])
    print(f"  {len(df_final):,} lignes chargées\n")

    # --- Import dans PostgreSQL via COPY (méthode optimisée) ---
    import io
    import time

    print("Import dans PostgreSQL (table : observations_meteo)...")
    print("   Méthode : COPY PostgreSQL (optimisé pour les gros volumes)\n")

    debut = time.time()

    # Étape 1 : Créer la table vide avec le bon schéma
    # head(0) envoie 0 lignes → crée juste la structure de la table
    df_final.head(0).to_sql(
        name="observations_meteo",
        con=engine,
        if_exists="replace",  # Recrée la table à chaque exécution
        index=False
    )

    # Étape 2 : Sérialiser le DataFrame en CSV dans un buffer mémoire
    # StringIO évite d'écrire un fichier temporaire sur le disque
    buffer = io.StringIO()
    df_final.to_csv(buffer, index=False, header=False)
    buffer.seek(0)  # Revenir au début du buffer avant la lecture par PostgreSQL

    # Étape 3 : Envoyer le buffer CSV à PostgreSQL via COPY
    # copy_expert() permet de passer une commande COPY SQL personnalisée
    # NULL '' indique que les chaînes vides doivent être traitées comme NULL en base
    with engine.connect() as conn:
        with conn.connection.cursor() as cursor:
            colonnes = ", ".join(df_final.columns)
            cursor.copy_expert(
                f"COPY observations_meteo ({colonnes}) FROM STDIN WITH CSV NULL ''",
                buffer
            )
        conn.connection.commit()  # Valider la transaction explicitement

    duree = time.time() - debut
    print(f"Import terminé en {duree:.1f} secondes !\n")

    # --- Vérification post-import ---
    # On interroge directement PostgreSQL pour confirmer que tout est bien arrivé
    with engine.connect() as conn:

        # Nombre total de lignes importées
        result = conn.execute(text("SELECT COUNT(*) FROM observations_meteo"))
        count = result.fetchone()[0]
        print(f"Nombre de lignes dans la table : {count:,}")

        # Période couverte et nombre de stations distinctes
        result = conn.execute(text("""
            SELECT MIN(date), MAX(date), COUNT(DISTINCT nom_usuel)
            FROM observations_meteo
        """))
        row = result.fetchone()
        print(f"Période couverte : {row[0]} → {row[1]}")
        print(f"Nombre de stations météo : {row[2]}")


# Point d'entrée du script
# Ce bloc s'exécute uniquement si le script est lancé directement
# (pas si importé comme module dans un autre script)
if __name__ == "__main__":
    main()