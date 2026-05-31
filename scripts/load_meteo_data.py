"""
Script de chargement des données Météo France dans PostgreSQL
Auteurs : Tharshan SIVAPALAN / Rayelen GUESMI
Projet : Mini-projet 4DVST - Data Visualization

Sources :
    - CSV local  : data/Q_01_previous-1950-2024_RR-T-Vent.csv (département 01)
    - API Météo France : départements définis dans .env

Méthode d'import : COPY PostgreSQL (optimisé pour les gros volumes)
    → Beaucoup plus rapide que to_sql() : ~35 secondes vs ~30 minutes
"""

import os
import io
import gzip
import time
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
    f"postgresql+psycopg2://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)

# Départements à télécharger via API (définis dans .env)
DEPARTEMENTS = os.getenv("DEPARTMENTS", "06,13,33,59,67,69,75").split(",")

# Option B — Tous les départements métropole (commenté)
# DEPARTEMENTS = [str(i).zfill(2) for i in range(1, 20)] + ["2A", "2B"] + [str(i).zfill(2) for i in range(21, 96)]

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 10000))

BASE_URL = "https://object.files.data.gouv.fr/meteofrance/data/synchro_ftp/BASE/QUOT"

# Colonnes utiles à conserver — inclut vent (ffm) et jours de gel (dg)
COLONNES_UTILES = [
    "NUM_POSTE", "NOM_USUEL", "LAT", "LON", "ALTI",
    "AAAAMMJJ",
    "TM",   # Température moyenne journalière (°C)
    "TX",   # Température maximale journalière (°C)
    "TN",   # Température minimale journalière (°C)
    "RR",   # Précipitations journalières (mm)
    "DG",   # Durée de gel dans la journée (minutes, T° < 0°C)
    "FFM",  # Vitesse moyenne du vent sur 10 min (m/s)
]


# ── Fonctions ────────────────────────────────────────────────────────────────

def download_and_parse(dep: str) -> pd.DataFrame | None:
    """Télécharge et parse le CSV d'un département via l'API Météo France."""
    url = f"{BASE_URL}/Q_{dep}_previous-1950-2024_RR-T-Vent.csv.gz"
    try:
        logger.info(f"Téléchargement département {dep}...")
        response = requests.get(url, timeout=60)
        response.raise_for_status()

        # na_values gère les codes de valeurs manquantes propres à Météo France
        # 'mq' / 'MQ' = "manquant" dans les fichiers Météo France
        with gzip.open(io.BytesIO(response.content), "rb") as f:
            colonnes_disponibles = pd.read_csv(f, sep=";", nrows=0).columns.tolist()
            colonnes_a_lire = [c for c in COLONNES_UTILES if c in colonnes_disponibles]

        with gzip.open(io.BytesIO(response.content), "rb") as f:
            df = pd.read_csv(
                f, sep=";",
                usecols=colonnes_a_lire,
                dtype=str,
                na_values=["", "mq", "MQ", "NaN"]
            )

        logger.info(f"Département {dep} téléchargé : {len(df):,} lignes brutes")
        return df

    except Exception as e:
        logger.warning(f"Département {dep} ignoré : {e}")
        return None


def load_local_file(filepath: str) -> pd.DataFrame | None:
    """Charge un fichier CSV local (données téléchargées manuellement)."""
    try:
        logger.info(f"Chargement fichier local : {filepath}")
        colonnes_disponibles = pd.read_csv(filepath, sep=";", nrows=0).columns.tolist()
        colonnes_a_lire = [c for c in COLONNES_UTILES if c in colonnes_disponibles]
        df = pd.read_csv(
            filepath, sep=";",
            usecols=colonnes_a_lire,
            dtype=str,
            na_values=["", "mq", "MQ", "NaN"]
        )
        return df
    except Exception as e:
        logger.error(f"Erreur lecture fichier local : {e}")
        return None


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Nettoyage technique minimal pour permettre l'insertion en base."""
    # Conversion de la date AAAAMMJJ → date Python
    if "AAAAMMJJ" in df.columns:
        df["date"] = pd.to_datetime(df["AAAAMMJJ"], format="%Y%m%d", errors="coerce")
        df["annee"] = df["date"].dt.year
        df["mois"] = df["date"].dt.month
        df.drop(columns=["AAAAMMJJ"], inplace=True)

    # Suppression des lignes sans date valide
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
        "RR": "precipitation",
        "DG": "duree_gel",
        "FFM": "vent_moyen"
    })

    # Conversion des colonnes numériques
    # str.replace(",", ".") gère les fichiers avec virgule comme séparateur décimal
    cols_numeriques = ["temp_moyenne", "temp_max", "temp_min",
                       "precipitation", "duree_gel", "vent_moyen",
                       "lat", "lon", "altitude"]
    for col in cols_numeriques:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "."),
                errors="coerce"
            )

    return df


def insert_copy(df: pd.DataFrame, engine, table: str):
    """
    Insère les données via COPY PostgreSQL.
    Beaucoup plus rapide que to_sql() pour les gros volumes :
    ~35 secondes vs ~30 minutes pour 3.6M lignes.
    """
    debut = time.time()

    # Sérialiser le DataFrame en CSV dans un buffer mémoire
    # StringIO évite d'écrire un fichier temporaire sur le disque
    buffer = io.StringIO()
    df.to_csv(buffer, index=False, header=False, na_rep="")
    buffer.seek(0)

    with engine.connect() as conn:
        with conn.connection.cursor() as cursor:
            colonnes = ", ".join(df.columns)
            cursor.copy_expert(
                f"COPY {table} ({colonnes}) FROM STDIN WITH CSV NULL ''",
                buffer
            )
        conn.connection.commit()

    duree = time.time() - debut
    logger.info(f"  → {len(df):,} lignes insérées en {duree:.1f}s via COPY ")


def is_department_loaded(engine, dep: str) -> bool:
    """Vérifie si un département est déjà chargé en base (évite les doublons)."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT COUNT(*) FROM observations_quotidiennes WHERE num_poste LIKE :dep"),
            {"dep": f"{dep}%"}
        )
        return result.scalar() > 0


def create_tables(engine):
    """Crée les tables, index et vues dans PostgreSQL si ils n'existent pas."""
    with engine.begin() as conn:
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
                precipitation FLOAT,
                duree_gel     FLOAT,
                vent_moyen    FLOAT
            );
        """))

        # Index pour accélérer les requêtes Metabase
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

        # Vue matérialisée agrégée annuelle par station
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
                ROUND(SUM(precipitation)::numeric, 1) AS precipitations_totales,
                ROUND(AVG(vent_moyen)::numeric, 2)    AS vent_moyen_annuel,
                SUM(CASE WHEN temp_min < 0 THEN 1 ELSE 0 END) AS jours_gel
            FROM observations_quotidiennes
            WHERE temp_moyenne IS NOT NULL
            GROUP BY num_poste, nom_station, lat, lon, annee
            ORDER BY annee;
        """))

    logger.info("Tables, index et vues créés avec succès.")


def main():
    engine = create_engine(DB_URL)
    create_tables(engine)

    # 1. Fichier local département 01 (CSV téléchargé manuellement)
    local_file = "data/Q_01_previous-1950-2024_RR-T-Vent.csv"
    if os.path.exists(local_file):
        if is_department_loaded(engine, "01"):
            logger.info("Département 01 déjà chargé — ignoré.")
        else:
            df = load_local_file(local_file)
            if df is not None:
                df = clean_dataframe(df)
                insert_copy(df, engine, "observations_quotidiennes")
                logger.info(f"Département 01 (local) chargé : {len(df):,} lignes ")

    # 2. Téléchargement via API pour les départements sélectionnés
    for dep in DEPARTEMENTS:
        if is_department_loaded(engine, dep):
            logger.info(f"Département {dep} déjà chargé — ignoré.")
            continue

        df = download_and_parse(dep)
        if df is not None:
            df = clean_dataframe(df)
            insert_copy(df, engine, "observations_quotidiennes")
            logger.info(f"Département {dep} chargé : {len(df):,} lignes ")

    # 3. Rafraîchissement vue matérialisée
    logger.info("Rafraîchissement de la vue moyennes_annuelles...")
    with engine.begin() as conn:
        conn.execute(text("REFRESH MATERIALIZED VIEW moyennes_annuelles;"))

    logger.info(" Chargement terminé avec succès !")


if __name__ == "__main__":
    main()