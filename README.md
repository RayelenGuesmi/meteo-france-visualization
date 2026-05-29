#  France is Warming Up — Météo France Dashboard

> **Data Visualization Project** | 4DVST | SUPINFO | 2025-2026

##  Project Overview

This project explores **climate change in France** through interactive data visualization. Using open data from Météo France, we built an interactive dashboard that tells the story of France's warming climate from 1950 to 2024.

**Story angle:** *"France is warming up — a story written in degrees"*

The dashboard follows a narrative structure:
1.  A disappearing winter — the hook
2.  Rising tension — temperature anomalies 1950→2024
3.  The climax — when records fall (2003, 2019, 2022, 2024)
4.  Multiple faces of warming — evidence from different angles
5.  Tomorrow — France at +2.7°C in 2050

---

##  Tech Stack

| Tool | Purpose |
|------|---------|
| **Metabase** | Interactive dashboard & visualizations |
| **PostgreSQL 15** | Data storage & aggregation |
| **Docker** | Containerization & deployment |
| **Python 3.12** | Data pipeline & preprocessing |
| **Météo France Open Data** | Source data (API + CSV) |

---

##  Data Sources

- **Météo France Open Data** — Daily observations from 2,400+ stations (1950–2024)
  - URL: https://meteo.data.gouv.fr/datasets/6569b51ae64326786e4e8e1a
  - Parameters: Temperature (min, max, avg), Precipitation, Wind
- **GeoJSON France** — Regional and departmental boundaries for maps

---

##  Getting Started

### Prerequisites
- Docker Desktop installed
- Python 3.8+
- Git

### 1. Clone the repository
```bash
git clone https://github.com/RayelenGuesmi/meteo-france-dashboard.git
cd meteo-france-dashboard
```

### 2. Start the infrastructure
```bash
docker-compose up -d
```

This will start:
- **PostgreSQL** on port 5436 (internal: 5432)
- **Metabase** on port 4200

### 3. Install Python dependencies
```bash
pip install pandas psycopg2-binary requests sqlalchemy
```

### 4. Download data and load into PostgreSQL
```bash
python scripts/load_meteo_data.py
```

The script will:
- Load the local CSV file for département 01 (Ain)
- Automatically download data for all other départements via the Météo France API
- Clean and transform the data
- Load ~95M rows into PostgreSQL
- Create aggregated materialized views for fast queries

### 5. Access Metabase
Open http://localhost:4200 and connect to the `meteo_france` database:
- Host: `postgres`
- Port: `5432`
- Database: `meteo_france`
- Username: `meteo_user`
- Password: `meteo_pass`

---

##  Project Structure

```
meteo-france-dashboard/
│
├── docker-compose.yml          # Infrastructure setup
├── README.md                   # Project documentation
│
├── init/
│   └── init.sql                # Database initialization (creates metabase_db)
│
├── scripts/
│   └── load_meteo_data.py      # Data pipeline (download, clean, load)
│
└── data/                       # Raw CSV files (not tracked in Git)
    └── Q_01_previous-1950-2024_RR-T-Vent.csv
```

---

##  Dashboard Visualizations

| Chart | Description |
|-------|-------------|
| **Temperature Trend 1950-2024** | Line chart showing average annual temperature evolution |
| **Station Temperatures Map** | Interactive pin map of weather stations colored by temperature |
| **Annual Precipitation 1950-2024** | Bar chart showing precipitation variability |
| **Max Temperature Records 1950-2024** | Line chart highlighting record-breaking years |

**Interactive filter:** Year selector to explore any time period across all charts simultaneously.

---

##  Agile Methodology

This project was managed using **SCRUM** over 5 weeks:

| Sprint | Duration | Goals |
|--------|----------|-------|
| Sprint 1 | Week 1 | Data exploration & storytelling definition |
| Sprint 2 | Week 2 | Infrastructure setup (Docker, PostgreSQL, Metabase) |
| Sprint 3 | Week 3 | Data pipeline & loading |
| Sprint 4 | Week 4 | Dashboard construction |
| Sprint 5 | Week 5 | Presentation & refinement |

---

##  Authors

- **Tharshan SIVAPALAN**
- **Rayelen GUESMI**

---

##  License

Open data from Météo France is licensed under [Licence Ouverte / Open Licence](https://www.etalab.gouv.fr/licence-ouverte-open-licence).