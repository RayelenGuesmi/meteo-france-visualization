"""
Script de nettoyage et standardisation des données Météo France (SQL natif)
Auteurs : Tharshan SIVAPALAN / Rayelen GUESMI
Projet : Mini-projet 4DVST - Data Visualization

Approche : nettoyage directement en SQL dans PostgreSQL + rapport qualité
Gain de temps : ~40 min (version Python) → ~3-5 min (version SQL)

Pipeline :
    load_meteo_data.py  →  clean_data.py  →  PostgreSQL (cleaned)
"""

import os
import logging
from datetime import datetime

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

# ── Seuils de validation météorologique ──────────────────────────────────────
# Basés sur les records historiques français et les limites physiques
SEUILS = {
    "temp_min":     {"min": -40.0, "max":  40.0},  # Record FR : -41°C (Mouthe, 1985)
    "temp_max":     {"min": -30.0, "max":  50.0},  # Record FR : +45.9°C (Gallargues, 2019)
    "temp_moyenne": {"min": -35.0, "max":  45.0},  # Entre TN et TX
    "precipitation":{"min":   0.0, "max": 500.0},  # Record journalier FR ~400mm
    "vent_moyen":   {"min":   0.0, "max": 100.0},  # Record FR ~75 m/s en rafale
}


# ── Fonctions ────────────────────────────────────────────────────────────────

def run_sql(engine, sql: str, label: str) -> int:
    """Exécute une requête SQL dans une transaction et log le résultat."""
    with engine.begin() as conn:
        result = conn.execute(text(sql))
    logger.info(f"{label} : {result.rowcount:,} lignes affectées")
    return result.rowcount


def get_stats(engine) -> dict:
    """Récupère les statistiques de la table depuis PostgreSQL."""
    with engine.connect() as conn:
        total = conn.execute(text(
            "SELECT COUNT(*) FROM observations_quotidiennes;"
        )).scalar()

        periode = conn.execute(text(
            "SELECT MIN(date), MAX(date) FROM observations_quotidiennes;"
        )).fetchone()

        stations = conn.execute(text(
            "SELECT COUNT(DISTINCT nom_station) FROM observations_quotidiennes;"
        )).scalar()

        quality = conn.execute(text("""
            SELECT data_quality, COUNT(*)
            FROM observations_quotidiennes
            GROUP BY data_quality
            ORDER BY 2 DESC;
        """)).fetchall()

        manquants = conn.execute(text("""
            SELECT
                ROUND(100.0 * SUM(CASE WHEN temp_moyenne  IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_tm,
                ROUND(100.0 * SUM(CASE WHEN temp_max      IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_tx,
                ROUND(100.0 * SUM(CASE WHEN temp_min      IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_tn,
                ROUND(100.0 * SUM(CASE WHEN precipitation IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_rr,
                ROUND(100.0 * SUM(CASE WHEN vent_moyen    IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_ffm,
                ROUND(100.0 * SUM(CASE WHEN duree_gel     IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_dg
            FROM observations_quotidiennes;
        """)).fetchone()

    return {
        "total": total,
        "periode_min": periode[0],
        "periode_max": periode[1],
        "stations": stations,
        "quality": quality,
        "manquants": manquants
    }


def generer_rapport(engine, stats_avant: dict, stats_apres: dict, corrections: dict):
    """
    Génère un rapport qualité détaillé dans rapport_qualite.txt.
    Inspiré de l'approche de Tharshan SIVAPALAN.
    """
    lignes_supprimees = stats_avant["total"] - stats_apres["total"]
    pct_conserve = (stats_apres["total"] / stats_avant["total"]) * 100

    rapport = [
        "=" * 70,
        "RAPPORT QUALITÉ — Données Météo France",
        f"Généré le : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70,
        "",
        "── RÉSUMÉ ──────────────────────────────────────────────────────────",
        f"Lignes initiales        : {stats_avant['total']:,}",
        f"Lignes après nettoyage  : {stats_apres['total']:,}",
        f"Lignes supprimées       : {lignes_supprimees:,}",
        f"Taux de conservation    : {pct_conserve:.1f}%",
        f"Période couverte        : {stats_apres['periode_min']} → {stats_apres['periode_max']}",
        f"Stations météo          : {stats_apres['stations']:,}",
        "",
        "── CORRECTIONS APPLIQUÉES ──────────────────────────────────────────",
    ]

    for label, count in corrections.items():
        rapport.append(f"  {label:<45} : {count:,}")

    rapport += [
        "",
        "── TAUX DE VALEURS MANQUANTES (après nettoyage) ────────────────────",
        f"  temp_moyenne  (TM) : {stats_apres['manquants'][0]}%",
        f"  temp_max      (TX) : {stats_apres['manquants'][1]}%",
        f"  temp_min      (TN) : {stats_apres['manquants'][2]}%",
        f"  precipitation (RR) : {stats_apres['manquants'][3]}%",
        f"  vent_moyen   (FFM) : {stats_apres['manquants'][4]}%",
        f"  duree_gel     (DG) : {stats_apres['manquants'][5]}%",
        "",
        "── DISTRIBUTION QUALITÉ ────────────────────────────────────────────",
    ]

    for row in stats_apres["quality"]:
        rapport.append(f"  {row[0]:<15} : {row[1]:,}")

    rapport += [
        "",
        "── SEUILS DE VALIDATION UTILISÉS ───────────────────────────────────",
    ]
    for col, bornes in SEUILS.items():
        rapport.append(f"  {col:<20} : [{bornes['min']}, {bornes['max']}]")

    rapport.append("=" * 70)

    with open("rapport_qualite.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(rapport))

    logger.info("Rapport qualité sauvegardé : rapport_qualite.txt")
    # Affiche le résumé dans le terminal
    for ligne in rapport[:15]:
        logger.info(ligne)


def main():
    engine = create_engine(DB_URL)
    logger.info("Démarrage du nettoyage optimisé (SQL natif)...")

    # Stats avant nettoyage
    stats_avant = get_stats(engine)
    logger.info(f"Lignes en base avant nettoyage : {stats_avant['total']:,}")

    corrections = {}

    # 1. Ajout colonne data_quality
    with engine.begin() as conn:
        conn.execute(text("""
            ALTER TABLE observations_quotidiennes
            ADD COLUMN IF NOT EXISTS data_quality VARCHAR(10) DEFAULT 'partial';
        """))
    logger.info("Colonne data_quality vérifiée/ajoutée.")

    # 2. Suppression lignes sans aucune mesure
    n = run_sql(engine, """
        DELETE FROM observations_quotidiennes
        WHERE temp_moyenne IS NULL
          AND temp_max      IS NULL
          AND temp_min      IS NULL
          AND precipitation IS NULL;
    """, "Lignes vides supprimées")
    corrections["Lignes sans aucune mesure supprimées"] = n

    # 3. Déduplication via DELETE USING (plus efficace que NOT IN sur gros volumes)
    n = run_sql(engine, """
        DELETE FROM observations_quotidiennes a
        USING observations_quotidiennes b
        WHERE a.id > b.id
          AND a.num_poste = b.num_poste
          AND a.date = b.date;
    """, "Doublons supprimés")
    corrections["Doublons supprimés (num_poste + date)"] = n

    # 4. Valeurs aberrantes → NULL (par colonne, selon seuils climatologiques)
    for col, bornes in SEUILS.items():
        n = run_sql(engine, f"""
            UPDATE observations_quotidiennes
            SET {col} = NULL
            WHERE {col} < {bornes['min']} OR {col} > {bornes['max']};
        """, f"Aberrants [{col}] corrigés")
        corrections[f"Valeurs aberrantes {col} → NULL"] = n

    # 5. Cohérence temp_min <= temp_max
    n = run_sql(engine, """
        UPDATE observations_quotidiennes
        SET temp_min = NULL, temp_max = NULL
        WHERE temp_min > temp_max;
    """, "Incohérences temp_min > temp_max corrigées")
    corrections["Incohérences temp_min > temp_max corrigées"] = n

    # 6. Standardisation noms de stations
    n = run_sql(engine, """
        UPDATE observations_quotidiennes
        SET nom_station = UPPER(TRIM(nom_station));
    """, "Noms de stations standardisés")
    corrections["Noms de stations standardisés (UPPER + TRIM)"] = n

    # 7. Flags qualité
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

    # 8. Rafraîchissement vue matérialisée
    with engine.begin() as conn:
        conn.execute(text("REFRESH MATERIALIZED VIEW moyennes_annuelles;"))
    logger.info("Vue matérialisée rafraîchie.")

    # 9. Stats après nettoyage + rapport qualité
    stats_apres = get_stats(engine)
    generer_rapport(engine, stats_avant, stats_apres, corrections)

    logger.info("─" * 50)
    logger.info(f"Total lignes en base : {stats_apres['total']:,}")
    logger.info("─" * 50)
    logger.info(" Nettoyage terminé avec succès !")


if __name__ == "__main__":
    main()