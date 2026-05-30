import pandas as pd
import glob
import os


# SEUILS DE VALIDATION CLIMATOLOGIQUE
SEUILS = {
    "tn":  {"min": -40.0,  "max": 40.0},   # Temp. min : record FR = -41°C (Mouthe, 1985)
    "tx":  {"min": -30.0,  "max": 50.0},   # Temp. max : record FR = 45.9°C (Gallargues, 2019)
    "tm":  {"min": -35.0,  "max": 45.0},   # Temp. moyenne : entre TN et TX
    "rr":  {"min": 0.0,    "max": 500.0},  # Précipitations : record journalier FR ~400mm
    "ffm": {"min": 0.0,    "max": 100.0},  # Vent moyen : record FR ~75 m/s en rafale
}

# Colonnes utiles à conserver (même liste que import_meteo.py)
COLONNES_UTILES = [
    "NUM_STA", "NOM_USUEL", "LAT", "LON", "ALTI",
    "AAAAMMJJ", "TN", "TX", "TM", "RR", "DG", "FFM",
]


def charger_fichiers_bruts():
    """
    Charge tous les fichiers .csv.gz du dossier courant et les fusionne.

    Returns:
        pd.DataFrame : DataFrame brut fusionné (avant nettoyage)
    """
    fichiers = glob.glob("*.csv.gz")
    if not fichiers:
        raise FileNotFoundError(" Aucun fichier .csv.gz trouvé dans le dossier courant.")

    print(f" {len(fichiers)} fichier(s) détecté(s)\n")
    dfs = []
    for f in sorted(fichiers):
        print(f"  Chargement : {os.path.basename(f)}")
        df = pd.read_csv(
            f,
            compression='gzip',
            sep=';',
            dtype=str,
            na_values=['', 'mq', 'MQ', 'NaN']
        )
        # Filtrer les colonnes utiles disponibles
        colonnes_presentes = [c for c in COLONNES_UTILES if c in df.columns]
        dfs.append(df[colonnes_presentes])
        print(f"     → {len(df):,} lignes\n")

    df_brut = pd.concat(dfs, ignore_index=True)
    print(f" Total brut : {len(df_brut):,} lignes\n")
    return df_brut


def convertir_types(df):
    """
    Convertit les colonnes en types appropriés.

    - AAAAMMJJ → datetime + extraction annee/mois
    - Colonnes numériques → float (avec gestion virgule/point)
    - Noms de colonnes → minuscules

    Args:
        df (pd.DataFrame) : DataFrame brut

    Returns:
        pd.DataFrame : DataFrame avec types convertis
    """
    print(" Conversion des types...")

    # --- Conversion de la date ---
    # errors="coerce" transforme les dates invalides en NaT (Not a Time)
    # au lieu de planter → on les détectera et supprimera ensuite
    if "AAAAMMJJ" in df.columns:
        df["date"] = pd.to_datetime(df["AAAAMMJJ"], format="%Y%m%d", errors="coerce")
        df["annee"] = df["date"].dt.year
        df["mois"]  = df["date"].dt.month
        df.drop(columns=["AAAAMMJJ"], inplace=True)

        dates_invalides = df["date"].isna().sum()
        if dates_invalides > 0:
            print(f"     {dates_invalides:,} dates invalides détectées (seront supprimées)")

    # --- Conversion des colonnes numériques ---
    for col in ["TN", "TX", "TM", "RR", "DG", "FFM", "LAT", "LON", "ALTI"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].str.replace(",", "."), errors="coerce")

    # --- Normalisation des noms de colonnes en minuscules ---
    df.columns = [c.lower() for c in df.columns]

    print("    Conversion terminée\n")
    return df


def supprimer_doublons(df, rapport):
    """
    Détecte et supprime les lignes dupliquées.
    Args:
        df (pd.DataFrame) : DataFrame à nettoyer
        rapport (list)    : Liste de logs pour le rapport qualité
    Returns:
        pd.DataFrame : DataFrame sans doublons
    """
    print(" Vérification des doublons...")

    avant = len(df)

    # On considère qu'une ligne est un doublon si station + date sont identiques
    # keep="first" conserve la première occurrence
    cles_dedup = [c for c in ["nom_usuel", "date"] if c in df.columns]
    df = df.drop_duplicates(subset=cles_dedup, keep="first")

    supprimes = avant - len(df)
    msg = f"Doublons supprimés : {supprimes:,} (sur {avant:,} lignes)"
    rapport.append(msg)

    if supprimes > 0:
        print(f"     {supprimes:,} doublons supprimés")
    else:
        print("    Aucun doublon détecté")

    print()
    return df


def gerer_valeurs_manquantes(df, rapport):
    """
    Analyse et traite les valeurs manquantes.
    Args:
        df (pd.DataFrame) : DataFrame à analyser
        rapport (list)    : Liste de logs pour le rapport qualité
    Returns:
        pd.DataFrame : DataFrame nettoyé
    """
    print(" Analyse des valeurs manquantes...")

    avant = len(df)

    # Rapport du taux de remplissage par colonne
    rapport.append("\n--- Taux de valeurs manquantes par colonne ---")
    for col in df.columns:
        nb_manquants = df[col].isna().sum()
        pct = (nb_manquants / len(df)) * 100
        msg = f"  {col:<15} : {nb_manquants:>10,} manquants ({pct:.1f}%)"
        rapport.append(msg)
        if pct > 50:
            print(f"     {col} : {pct:.1f}% de valeurs manquantes")

    # Suppression des lignes sans date (non exploitables pour les séries temporelles)
    if "date" in df.columns:
        df = df.dropna(subset=["date"])
        supprimes_date = avant - len(df)
        if supprimes_date > 0:
            msg = f"Lignes supprimées (date manquante) : {supprimes_date:,}"
            rapport.append(msg)
            print(f"     {supprimes_date:,} lignes sans date supprimées")

    # Suppression des lignes sans nom de station
    if "nom_usuel" in df.columns:
        avant_station = len(df)
        df = df.dropna(subset=["nom_usuel"])
        supprimes_station = avant_station - len(df)
        if supprimes_station > 0:
            msg = f"Lignes supprimées (station manquante) : {supprimes_station:,}"
            rapport.append(msg)
            print(f"     {supprimes_station:,} lignes sans station supprimées")

    print("    Valeurs manquantes traitées\n")
    return df


def supprimer_valeurs_aberrantes(df, rapport):
    """
    Détecte et supprime les valeurs climatologiquement impossibles.
    Args:
        df (pd.DataFrame) : DataFrame à nettoyer
        rapport (list)    : Liste de logs pour le rapport qualité

    Returns:
        pd.DataFrame : DataFrame sans valeurs aberrantes
    """
    print(" Détection des valeurs aberrantes...")

    rapport.append("\n--- Valeurs aberrantes supprimées ---")
    total_aberrants = 0

    for col, bornes in SEUILS.items():
        if col not in df.columns:
            continue

        # Compte les valeurs hors bornes (en ignorant les NaN)
        masque_aberrant = (
            df[col].notna() &
            ((df[col] < bornes["min"]) | (df[col] > bornes["max"]))
        )
        nb_aberrants = masque_aberrant.sum()

        if nb_aberrants > 0:
            # On met les valeurs aberrantes à NaN plutôt que de supprimer toute la ligne
            # (une ligne peut avoir TX aberrant mais TN et RR valides)
            df.loc[masque_aberrant, col] = None
            msg = f"  {col} : {nb_aberrants:,} valeurs hors [{bornes['min']}, {bornes['max']}] → mises à NaN"
            rapport.append(msg)
            print(f"     {col} : {nb_aberrants:,} valeurs aberrantes neutralisées")
            total_aberrants += nb_aberrants

    if total_aberrants == 0:
        print("    Aucune valeur aberrante détectée")

    rapport.append(f"  Total : {total_aberrants:,} valeurs aberrantes neutralisées")
    print()
    return df


def generer_rapport(rapport, df_final, nb_lignes_initial):
    """
    Génère et sauvegarde le rapport qualité dans rapport_qualite.txt.

    Args:
        rapport (list)       : Liste de logs accumulés pendant le nettoyage
        df_final (DataFrame) : DataFrame final après nettoyage
        nb_lignes_initial (int) : Nombre de lignes avant nettoyage
    """
    lignes_supprimees = nb_lignes_initial - len(df_final)
    pct_conserve = (len(df_final) / nb_lignes_initial) * 100

    resume = [
        "RAPPORT QUALITÉ — Données Météo France",
        f"Lignes initiales        : {nb_lignes_initial:,}",
        f"Lignes après nettoyage  : {len(df_final):,}",
        f"Lignes supprimées       : {lignes_supprimees:,}",
        f"Taux de conservation    : {pct_conserve:.1f}%",
        f"Colonnes finales        : {list(df_final.columns)}",
        f"Période couverte        : {df_final['date'].min()} → {df_final['date'].max()}",
        f"Stations météo          : {df_final['nom_usuel'].nunique():,}",
    ] + rapport

    with open("rapport_qualite.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(resume))

    print(" Rapport qualité sauvegardé : rapport_qualite.txt")
    print("\n".join(resume[:10]))  # Affiche le résumé dans le terminal


def main():
    rapport = []

    # --- Chargement ---
    df = charger_fichiers_bruts()
    nb_lignes_initial = len(df)

    # --- Pipeline de nettoyage ---
    df = convertir_types(df)
    df = supprimer_doublons(df, rapport)
    df = gerer_valeurs_manquantes(df, rapport)
    df = supprimer_valeurs_aberrantes(df, rapport)

    # --- Sauvegarde des données nettoyées ---
    print(" Sauvegarde des données nettoyées...")
    df.to_csv("data_nettoyee.csv", index=False)
    print(f"    Fichier sauvegardé : data_nettoyee.csv ({len(df):,} lignes)\n")

    # --- Rapport qualité ---
    generer_rapport(rapport, df, nb_lignes_initial)


if __name__ == "__main__":
    main()