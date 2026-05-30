"""
Script de chargement des données Météo France dans PostgreSQL
Auteurs : Tharshan SIVAPALAN / Rayelen GUESMI
Projet : Mini-projet 4DVST - Data Visualization

Sources :
    - CSV local  : data/Q_01_previous-1950-2024_RR-T-Vent.csv (département 01)
    - API Météo France : départements définis dans .env
"""

import os
import gzip
import io
import logging

import pandas as pd
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# ── Configuration ────────────────────────────────────────────────────────────
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DB_URL = (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)

# Départements à télécharger via API (définis dans .env)
DEPARTEMENTS = os.getenv("DEPARTMENTS", "06,13,33,59,67,69,75").split(",")

# Option B — Tous les départements (commenté)
# DEPARTEMENTS = [str(i).zfill(2) for i in range(1, 20)] + ["2A", "2B"] + [str(i).zfill(2) for i in range(21, 96)]

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 10000))

BASE_URL = "https://object.files.data.gouv.fr/meteofrance/data/synchro_ftp/BASE/QUOT"

COLONNES_UTILES = [
    "NUM_POSTE", "NOM_USUEL", "LAT", "LON", "ALTI",
    "AAAAMMJJ", "TM", "TX", "TN", "RR"
]


# ── Fonctions ────────────────────────────────────────────────────────────────

def download_and_parse(dep: str) -> pd.DataFrame | None:
    """Télécharge et parse le CSV d'un département via l'API Météo France."""
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


def load_local_file(filepath: str) -> pd.DataFrame | None:
    """Charge un fichier CSV local (données téléchargées manuellement)."""
    try:
        logger.info(f"Chargement fichier local : {filepath}")
        df = pd.read_csv(filepath, sep=";", usecols=COLONNES_UTILES, dtype={"NUM_POSTE": str})
        return df
    except Exception as e:
        logger.error(f"Erreur lecture fichier local : {e}")
        return None


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Nettoyage technique minimal pour permettre l'insertion en base."""
    df["date"] = pd.to_datetime(df["AAAAMMJJ"].astype(str), format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["date"])

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

    df = df.drop(columns=["AAAAMMJJ"])
    df["annee"] = df["date"].dt.year
    df["mois"] = df["date"].dt.month

    for col in ["temp_moyenne", "temp_max", "temp_min", "precipitation"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def is_department_loaded(engine, dep: str) -> bool:
    """Vérifie si un département est déjà chargé en base (évite les doublons)."""
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT COUNT(*) FROM observations_quotidiennes WHERE num_poste LIKE :dep"
        ), {"dep": f"{dep}%"})
        count = result.scalar()
    return count > 0


def create_tables(engine):
    """Crée les tables et vues dans PostgreSQL si elles n'existent pas."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS observations_quotidiennes (
                id            SERIAL PRIMARY KEY,
                num_poste     VARCHAR(10),
                nom_station   VARCHAR(100),
                lat           FLOAT,
                lon           FLOAT,
                altitude      FLOAT,
                date          DATE,
                annee         INT,
                mois          INT,
                temp_moyenne  FLOAT,
                temp_max      FLOAT,
                temp_min      FLOAT,
                precipitation FLOAT
            );
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_poste_date
            ON observations_quotidiennes(num_poste, date);
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_annee
            ON observations_quotidiennes(annee);
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_mois
            ON observations_quotidiennes(mois);
        """))

        conn.execute(text("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS moyennes_annuelles AS
            SELECT
                num_poste,
                nom_station,
                lat,
                lon,
                AVG(altitude)                         AS altitude,
                annee,
                ROUND(AVG(temp_moyenne)::numeric, 2)  AS temp_moy_annuelle,
                ROUND(AVG(temp_max)::numeric, 2)      AS temp_max_annuelle,
                ROUND(AVG(temp_min)::numeric, 2)      AS temp_min_annuelle,
                ROUND(SUM(precipitation)::numeric, 1) AS precipitations_totales
            FROM observations_quotidiennes
            WHERE temp_moyenne IS NOT NULL
            GROUP BY num_poste, nom_station, lat, lon, annee
            ORDER BY annee;
        """))
        conn.commit()

    logger.info("Tables, index et vues créés avec succès.")


def main():
    engine = create_engine(DB_URL)
    create_tables(engine)

    # 1. Fichier local département 01
    local_file = "data/Q_01_previous-1950-2024_RR-T-Vent.csv"
    if os.path.exists(local_file):
        if is_department_loaded(engine, "01"):
            logger.info("Département 01 déjà chargé — ignoré.")
        else:
            df = load_local_file(local_file)
            if df is not None:
                df = clean_dataframe(df)
                df.to_sql("observations_quotidiennes", engine,
                          if_exists="append", index=False,
                          chunksize=CHUNK_SIZE, method="multi")
                logger.info(f"Département 01 (local) chargé : {len(df):,} lignes ")

    # 2. Téléchargement via API
    for dep in DEPARTEMENTS:
        if is_department_loaded(engine, dep):
            logger.info(f"Département {dep} déjà chargé — ignoré.")
            continue

        df = download_and_parse(dep)
        if df is not None:
            df = clean_dataframe(df)
            df.to_sql("observations_quotidiennes", engine,
                      if_exists="append", index=False,
                      chunksize=CHUNK_SIZE, method="multi")
            logger.info(f"Département {dep} chargé : {len(df):,} lignes ")

    # 3. Rafraîchissement vue matérialisée
    logger.info("Rafraîchissement de la vue moyennes_annuelles...")
    with engine.connect() as conn:
        conn.execute(text("REFRESH MATERIALIZED VIEW moyennes_annuelles;"))
        conn.commit()

    logger.info(" Chargement terminé avec succès !")


if __name__ == "__main__":
    main()