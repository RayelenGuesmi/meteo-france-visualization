"""
Script de nettoyage optimisé des données Météo France (SQL natif)
Auteurs : Tharshan SIVAPALAN / Rayelen GUESMI
Projet : Mini-projet 4DVST - Data Visualization

Approche : nettoyage directement en SQL dans PostgreSQL
Gain de temps : ~40 min (version Python) → ~3-5 min (version SQL)

Pipeline :
    load_meteo_data.py  →  clean_data.py  →  PostgreSQL (cleaned)
"""

import os
import logging

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

# ── Seuils de validation météorologique ──────────────────────────────────────
TEMP_MIN_VALID   = -40.0   # Record absolu France : -41°C (Mouthe, 1985)
TEMP_MAX_VALID   =  50.0   # Record absolu France : 45.9°C (2019) + marge
PRECIP_MAX_VALID = 500.0   # Record journalier France : ~300mm


def run_sql(engine, sql: str, label: str) -> int:
    """Exécute une requête SQL dans une transaction et log le résultat."""
    with engine.begin() as conn:
        result = conn.execute(text(sql))
    logger.info(f"{label} : {result.rowcount:,} lignes affectées")
    return result.rowcount


def main():
    engine = create_engine(DB_URL)
    logger.info("Démarrage du nettoyage optimisé (SQL natif)...")

    # 1. Ajout colonne data_quality
    with engine.begin() as conn:
        conn.execute(text("""
            ALTER TABLE observations_quotidiennes
            ADD COLUMN IF NOT EXISTS data_quality VARCHAR(10) DEFAULT 'partial';
        """))
    logger.info("Colonne data_quality vérifiée/ajoutée.")

    # 2. Suppression lignes sans aucune mesure
    run_sql(engine, """
        DELETE FROM observations_quotidiennes
        WHERE temp_moyenne IS NULL
          AND temp_max      IS NULL
          AND temp_min      IS NULL
          AND precipitation IS NULL;
    """, "Lignes vides supprimées")

    # 3. Déduplication via DELETE USING
    run_sql(engine, """
        DELETE FROM observations_quotidiennes a
        USING observations_quotidiennes b
        WHERE a.id > b.id
          AND a.num_poste = b.num_poste
          AND a.date = b.date;
    """, "Doublons supprimés")

    # 4. Températures aberrantes → NULL
    run_sql(engine, f"""
        UPDATE observations_quotidiennes SET
            temp_moyenne = CASE
                WHEN temp_moyenne < {TEMP_MIN_VALID} OR temp_moyenne > {TEMP_MAX_VALID}
                THEN NULL ELSE temp_moyenne END,
            temp_max = CASE
                WHEN temp_max < {TEMP_MIN_VALID} OR temp_max > {TEMP_MAX_VALID}
                THEN NULL ELSE temp_max END,
            temp_min = CASE
                WHEN temp_min < {TEMP_MIN_VALID} OR temp_min > {TEMP_MAX_VALID}
                THEN NULL ELSE temp_min END
        WHERE temp_moyenne < {TEMP_MIN_VALID} OR temp_moyenne > {TEMP_MAX_VALID}
           OR temp_max     < {TEMP_MIN_VALID} OR temp_max     > {TEMP_MAX_VALID}
           OR temp_min     < {TEMP_MIN_VALID} OR temp_min     > {TEMP_MAX_VALID};
    """, "Températures aberrantes corrigées")

    # 5. Précipitations aberrantes → NULL
    run_sql(engine, f"""
        UPDATE observations_quotidiennes
        SET precipitation = NULL
        WHERE precipitation < 0 OR precipitation > {PRECIP_MAX_VALID};
    """, "Précipitations aberrantes corrigées")

    # 6. Incohérence temp_min > temp_max → NULL
    run_sql(engine, """
        UPDATE observations_quotidiennes
        SET temp_min = NULL, temp_max = NULL
        WHERE temp_min > temp_max;
    """, "Incohérences temp_min > temp_max corrigées")

    # 7. Standardisation noms de stations
    run_sql(engine, """
        UPDATE observations_quotidiennes
        SET nom_station = UPPER(TRIM(nom_station));
    """, "Noms de stations standardisés")

    # 8. Flags qualité
    run_sql(engine, """
        UPDATE observations_quotidiennes
        SET data_quality = CASE
            WHEN temp_moyenne IS NOT NULL
             AND temp_max     IS NOT NULL
             AND temp_min     IS NOT NULL
             AND precipitation IS NOT NULL
            THEN 'complete'
            ELSE 'partial'
        END;
    """, "Flags qualité mis à jour")

    # 9. Rafraîchissement vue matérialisée
    with engine.begin() as conn:
        conn.execute(text("REFRESH MATERIALIZED VIEW moyennes_annuelles;"))
    logger.info("Vue matérialisée rafraîchie.")

    # 10. Stats finales
    with engine.connect() as conn:
        total = conn.execute(text(
            "SELECT COUNT(*) FROM observations_quotidiennes;"
        )).scalar()
        quality = conn.execute(text("""
            SELECT data_quality, COUNT(*)
            FROM observations_quotidiennes
            GROUP BY data_quality
            ORDER BY 2 DESC;
        """)).fetchall()

    logger.info("─" * 50)
    logger.info(f"Total lignes en base : {total:,}")
    for row in quality:
        logger.info(f"  {row[0]:<10} : {row[1]:,}")
    logger.info("─" * 50)
    logger.info(" Nettoyage terminé avec succès !")


if __name__ == "__main__":
    main()