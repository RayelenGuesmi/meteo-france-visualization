# 🌡️ Réchauffement Climatique en France — Météo France x Metabase

Projet final 4DVST - Data Visualization

## Stack technique
- **PostgreSQL 15** — Stockage des données climatologiques (3.6M lignes)
- **Metabase** — Dashboards interactifs
- **pgAdmin 4** — Administration PostgreSQL (optionnel)
- **Python 3** — Import et nettoyage des données

---

##  Prérequis avant de commencer

### Outils à installer
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installé et lancé
- Python 3.10+

### Données à télécharger manuellement

Les fichiers CSV ne sont pas inclus dans le repo (trop lourds). Il faut les télécharger depuis [meteo.data.gouv.fr](https://meteo.data.gouv.fr/datasets/donnees-climatologiques-de-base-quotidiennes) **avant de lancer le projet**.

Télécharge les 8 fichiers suivants et place-les à la **racine du projet** :

| Fichier | Département | Période |
|---|---|---|
| `Q_13_previous-1950-2024_RR-T-Vent.csv.gz` | Bouches-du-Rhône (13) | 1950-2024 |
| `Q_13_latest-2025-2026_RR-T-Vent.csv.gz` | Bouches-du-Rhône (13) | 2025-2026 |
| `Q_29_previous-1950-2024_RR-T-Vent.csv.gz` | Finistère (29) | 1950-2024 |
| `Q_29_latest-2025-2026_RR-T-Vent.csv.gz` | Finistère (29) | 2025-2026 |
| `Q_31_previous-1950-2024_RR-T-Vent.csv.gz` | Haute-Garonne (31) | 1950-2024 |
| `Q_31_latest-2025-2026_RR-T-Vent.csv.gz` | Haute-Garonne (31) | 2025-2026 |
| `Q_75_previous-1950-2024_RR-T-Vent.csv.gz` | Paris (75) | 1950-2024 |
| `Q_75_latest-2025-2026_RR-T-Vent.csv.gz` | Paris (75) | 2025-2026 |

>  Ces fichiers sont dans le `.gitignore` — chaque membre du groupe doit les télécharger de son côté.

---

## 🚀 Installation et démarrage

### Étape 1 — Cloner le repo

```bash
git clone https://github.com/TON_BINOME/NOM_DU_REPO.git
cd NOM_DU_REPO
```

### Étape 2 — Créer et activer le venv Python

```bash
python3 -m venv venv
source venv/bin/activate      # Mac/Linux
# venv\Scripts\activate       # Windows
```

### Étape 3 — Installer les dépendances Python

```bash
pip install -r requirements.txt
```

### Étape 4 — Lancer les services Docker

```bash
docker-compose up -d
```

Vérifie que les 3 services tournent :
```bash
docker-compose ps
```
Tu dois voir `postgres_meteo`, `metabase` et `pgadmin_meteo` avec le statut `Up`.

### Étape 5 — Nettoyer et importer les données

```bash
# Nettoyage des données brutes → génère data_nettoyee.csv + rapport_qualite.txt
python clean_data.py

# Import dans PostgreSQL → charge data_nettoyee.csv dans la table observations_meteo
python import_meteo.py
```

>  Le nettoyage prend ~2 min, l'import ~30-60 sec grâce à la commande COPY PostgreSQL.

### Étape 6 — Accéder aux interfaces

| Service  | URL                   | Identifiants           |
|----------|-----------------------|------------------------|
| Metabase | http://localhost:3000 | (compte créé au setup) |
| pgAdmin  | http://localhost:5050 | admin@meteo.fr / admin |

---

##  Structure du projet

```
PROJET_FINAL_4DVST/
│
├──  docker-compose.yml           # Orchestration PostgreSQL + Metabase + pgAdmin
├──  requirements.txt             # Dépendances Python (pandas, sqlalchemy, psycopg2)
├──  .gitignore                   # Fichiers exclus du repo
├──  README.md                    # Ce fichier
│
├──  clean_data.py                # Étape 1 : nettoyage des données brutes
├──  import_meteo.py              # Étape 2 : import dans PostgreSQL via COPY
│
├──  data_nettoyee.csv            #  Généré par clean_data.py (ignoré par git)
├──  rapport_qualite.txt          #  Rapport de nettoyage (ignoré par git)
│
├──  Q_13_*.csv.gz               #  À télécharger — Bouches-du-Rhône (ignoré par git)
├──  Q_29_*.csv.gz               #  À télécharger — Finistère (ignoré par git)
├──  Q_31_*.csv.gz               #  À télécharger — Haute-Garonne (ignoré par git)
├──  Q_75_*.csv.gz               #  À télécharger — Paris (ignoré par git)
│
└──  venv/                        #  Environnement virtuel Python (ignoré par git)
```

---

## 🔧 Commandes Docker utiles

```bash
# Démarrer les services
docker-compose up -d

# Arrêter les services (données conservées)
docker-compose down

# Voir les logs en temps réel
docker-compose logs -f

# Redémarrer un service spécifique
docker-compose restart metabase

# Réinitialiser complètement ( supprime toutes les données)
docker-compose down -v
```

---

## 📊 Connexion Metabase → PostgreSQL

Dans Metabase : **Admin → Bases de données → Ajouter une base de données**

| Champ        | Valeur        |
|--------------|---------------|
| Type         | PostgreSQL    |
| Hôte         | `postgres`    |
| Port         | `5432`        |
| Base         | `meteo`       |
| Utilisateur  | `meteo_admin` |
| Mot de passe | `meteo_admin` |

> ⚠️ Dans le docker-compose, utilise `postgres` comme hôte (nom du service Docker).
> Pour les scripts Python lancés depuis ta machine, utilise `localhost` avec le port `5433`.

