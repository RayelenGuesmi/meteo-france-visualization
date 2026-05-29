import pandas as pd
import requests
import os
import gzip
import io
from sqlalchemy import create_engine, text
import logging

#  Configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DB_URL = "postgresql://meteo_user:meteo_pass@localhost:5436/meteo_france"

#  Sélection des départements

# Option A — 7 départements représentatifs (ACTIF)
# Couvre toutes les régions climatiques de France métropolitaine :
# Nord, Sud-Est, Sud-Ouest, Ouest, Est, Centre-Est, Île-de-France

DEPARTEMENTS = [
    "06",  # Alpes-Maritimes — Nice (Méditerranée, le plus chaud)
    "13",  # Bouches-du-Rhône — Marseille (Sud méditerranéen)
    "33",  # Gironde — Bordeaux (Atlantique, vignes & vendanges)
    "59",  # Nord — Lille (contraste climatique Nord/Sud)
    "67",  # Bas-Rhin — Strasbourg (climat continental, Est)
    "69",  # Rhône — Lyon (Centre-Est, carrefour climatique)
    "75",  # Paris — référence nationale historique
]

# Option B — Tous les départements métropole
# DEPARTEMENTS = [str(i).zfill(2) for i in range(1, 20)] + ["2A", "2B"] + [str(i).zfill(2) for i in range(21, 96)]

BASE_URL = "https://object.files.data.gouv.fr/meteofrance/data/synchro_ftp/BASE/QUOT"

COLONNES_UTILES = [
    "NUM_POSTE", "NOM_USUEL", "LAT", "LON", "ALTI",
    "AAAAMMJJ", "TM", "TX", "TN", "RR"
]

#  Fonctions

def download_and_parse(dep: str) -> pd.DataFrame | None:
    """Télécharge et parse le CSV d'un département via l'API Météo France (période 1950-2024)."""
    url = f"{BASE_URL}/Q_{dep}_previous-1950-2024_RR-T-Vent.csv.gz"
    try:
        logger.info(f"Téléchargement département {dep}...")
        response = requests.get(url, timeout=60)
        response.raise_for_status()

        with gzip.open(io.BytesIO(response.content), "rb") as f:
            df = pd.read_csv(f, sep=";", usecols=COLONNES_UTILES, dtype={"NUM_POSTE": str})

        logger.info(f"Département {dep} téléchargé : {len(df):,} lignes brutes")
        return df

    except Exception as e:
        logger.warning(f"Département {dep} ignoré : {e}")
        return None


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Nettoie et transforme le DataFrame."""
    # Conversion de la date AAAAMMJJ → date Python
    df["date"] = pd.to_datetime(df["AAAAMMJJ"].astype(str), format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["date"])

    # Renommage des colonnes en minuscules
    df = df.rename(columns={
        "NUM_POSTE": "num_poste",
        "NOM_USUEL": "nom_station",
        "LAT": "lat",
        "LON": "lon",
        "ALTI": "altitude",
        "TM": "temp_moyenne",
        "TX": "temp_max",
        "TN": "temp_min",
        "RR": "precipitation"
    })

    # Suppression de la colonne AAAAMMJJ
    df = df.drop(columns=["AAAAMMJJ"])

    # Extraction de l'année et du mois pour les agrégations dans Metabase
    df["annee"] = df["date"].dt.year
    df["mois"] = df["date"].dt.month

    # Conversion des valeurs numériques
    for col in ["temp_moyenne", "temp_max", "temp_min", "precipitation"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def load_local_file(filepath: str) -> pd.DataFrame | None:
    """Charge un fichier CSV local (données téléchargées manuellement)."""
    try:
        logger.info(f"Chargement fichier local : {filepath}")
        df = pd.read_csv(filepath, sep=";", usecols=COLONNES_UTILES, dtype={"NUM_POSTE": str})
        return df
    except Exception as e:
        logger.error(f"Erreur lecture fichier local : {e}")
        return None


def create_tables(engine):
    """Crée les tables et vues dans PostgreSQL si elles n'existent pas."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS observations_quotidiennes (
                id SERIAL PRIMARY KEY,
                num_poste VARCHAR(10),
                nom_station VARCHAR(100),
                lat FLOAT,
                lon FLOAT,
                altitude FLOAT,
                date DATE,
                annee INT,
                mois INT,
                temp_moyenne FLOAT,
                temp_max FLOAT,
                temp_min FLOAT,
                precipitation FLOAT
            );
        """))
        conn.commit()

    # Vue agrégée annuelle par station (utilisée par Metabase)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS moyennes_annuelles AS
            SELECT
                num_poste,
                nom_station,
                lat,
                lon,
                AVG(altitude)                          AS altitude,
                annee,
                ROUND(AVG(temp_moyenne)::numeric, 2)   AS temp_moy_annuelle,
                ROUND(AVG(temp_max)::numeric, 2)       AS temp_max_annuelle,
                ROUND(AVG(temp_min)::numeric, 2)       AS temp_min_annuelle,
                ROUND(SUM(precipitation)::numeric, 1)  AS precipitations_totales
            FROM observations_quotidiennes
            WHERE temp_moyenne IS NOT NULL
            GROUP BY num_poste, nom_station, lat, lon, annee
            ORDER BY annee;
        """))
        conn.commit()

    logger.info("Tables et vues créées avec succès.")


def main():
    engine = create_engine(DB_URL)
    create_tables(engine)

    # 1. Fichier local département 01 (téléchargé manuellement via CSV)
    local_file = "data/Q_01_previous-1950-2024_RR-T-Vent.csv"
    if os.path.exists(local_file):
        df = load_local_file(local_file)
        if df is not None:
            df = clean_dataframe(df)
            df.to_sql("observations_quotidiennes", engine,
                      if_exists="append", index=False,
                      chunksize=10_000, method="multi")
            logger.info(f"Département 01 (local) chargé : {len(df):,} lignes")

    # 2. Téléchargement via API pour les départements sélectionnés
    for dep in DEPARTEMENTS:
        df = download_and_parse(dep)
        if df is not None:
            df = clean_dataframe(df)
            df.to_sql("observations_quotidiennes", engine,
                      if_exists="append", index=False,
                      chunksize=10_000, method="multi")
            logger.info(f"Département {dep} chargé : {len(df):,} lignes ")

    # 3. Rafraîchissement de la vue matérialisée
    logger.info("Rafraîchissement de la vue moyennes_annuelles...")
    with engine.connect() as conn:
        conn.execute(text("REFRESH MATERIALIZED VIEW moyennes_annuelles;"))
        conn.commit()

    logger.info(" Chargement terminé avec succès !")


if __name__ == "__main__":
    main()