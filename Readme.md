# Réchauffement Climatique en France — Météo France x Metabase

Projet final 4DVST - Data Visualization

## Stack technique
- **PostgreSQL 15** — Stockage des données climatologiques (3.6M lignes)
- **Metabase** — Dashboards interactifs
- **pgAdmin 4** — Administration PostgreSQL (optionnel)
- **Python 3** — Import et nettoyage des données

---

##  Démarrage rapide

### 1. Prérequis
- Docker Desktop installé et lancé
- Python 3.10+ avec venv

### 2. Lancer les services
```bash
docker-compose up -d
```

### 3. Vérifier que tout tourne
```bash
docker-compose ps
```
Tu dois voir 3 services `Up` : `postgres_meteo`, `metabase`, `pgadmin_meteo`

### 4. Activer le venv et importer les données
```bash
source venv/bin/activate
python clean_data.py    # Nettoyage des données brutes
python import_meteo.py  # Import dans PostgreSQL
```

### 5. Accéder aux interfaces
| Service   | URL                    | Identifiants          |
|-----------|------------------------|-----------------------|
| Metabase  | http://localhost:3000  | (compte créé au setup)|
| pgAdmin   | http://localhost:5050  | admin@meteo.fr / admin|

---

##  Structure du projet
```
PROJET_FINAL_4DVST/
├── docker-compose.yml          # Orchestration des services
├── requirements.txt            # Dépendances Python
├── clean_data.py               # Nettoyage des données brutes
├── import_meteo.py             # Import dans PostgreSQL
├── data_nettoyee.csv           # Données nettoyées (généré par clean_data.py)
├── rapport_qualite.txt         # Rapport de nettoyage (généré par clean_data.py)
├── venv/                       # Environnement virtuel Python
└── Q_*.csv.gz                  # Données brutes Météo France
```

---

##  Commandes utiles

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

##  Connexion Metabase → PostgreSQL

Dans Metabase Admin → Bases de données → Ajouter :

| Champ      | Valeur        |
|------------|---------------|
| Type       | PostgreSQL    |
| Hôte       | `postgres`    |
| Port       | `5432`        |
| Base       | `meteo`       |
| Utilisateur| `meteo_admin` |
| Mot de passe| `meteo_admin`|

>  Dans le docker-compose, utilise `postgres` comme hôte (nom du service).
> En dehors de Docker (script Python), utilise `localhost` avec le port `5433`.