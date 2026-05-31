#  France is Warming Up — Météo France Visualization

> **Data Visualization Project** | 4DVST | SUPINFO | 2025-2026


##  Project Overview

This project explores **climate change in France** through interactive data visualization. Using open data from Météo France, we built an interactive Metabase dashboard that tells the story of France's warming climate from 1950 to 2024.

**Story angle:** *"France is warming up — a story written in degrees"*

The dashboard follows a 4-act narrative structure:
1.  **Warming Story** — Temperature trend 1950→2024, station map, precipitation
2.  **Regional Comparison** — City-by-city climate differences across France
3.  **Extreme Events** — Heatwaves, records, hot days, frost days, wind speed
4.  **Precipitation Patterns** — Droughts, floods, seasonal patterns

---

##  Project Structure

```
meteo-france-visualization/
│
├── docker-compose.yml          # Infrastructure: PostgreSQL + Metabase
├── README.md                   # Project documentation
├── .gitignore                  # Excludes raw CSV files (too large for GitHub)
├── .env.example                # Environment variables template
├── requirements.txt            # Python dependencies
├── rapport_qualite.txt         # Auto-generated data quality report
│
├── init/
│   └── init.sql                # Creates metabase_db at container startup
│
├── scripts/
│   ├── load_meteo_data.py      # Step 1: Download & load raw data into PostgreSQL
│   └── clean_data.py           # Step 2: Clean, validate & standardize data
│
├── data/                       # Raw CSV files (not tracked in Git — too large)
│   └── Q_01_previous-1950-2024_RR-T-Vent.csv  # Dept 01 — manually downloaded
│
└── Captures/                   # Dashboard & script screenshots
    ├── Dashboard Warming Story.png
    ├── Dashboard Regional Comparison.png
    ├── Dashboard Extreme Events.png
    ├── Dashboard Precipitation.png
    ├── script load_meteo_data.png
    └── script clean_data.png
```

---

##  Data Pipeline

The project follows a clean **Extract → Load → Clean → Visualize** pipeline:

```
meteo.data.gouv.fr
        │
        ├── CSV (dept 01) — manual download
        └── API (depts 06, 13, 33, 59, 67, 69, 75) — automatic
                │
                ▼
        load_meteo_data.py
        (technical cleaning: date parsing, column renaming,
         numeric conversion, year/month extraction)
        Uses COPY PostgreSQL for fast insertion (~3 min vs ~30 min)
                │
                ▼
        PostgreSQL — observations_quotidiennes (raw)
                │
                ▼
        clean_data.py
        (business cleaning: deduplication, outlier removal,
         coherence checks, name standardization, quality flags)
        Generates rapport_qualite.txt automatically
                │
                ▼
        PostgreSQL — observations_quotidiennes (clean)
        + moyennes_annuelles (materialized view)
                │
                ▼
        Metabase Dashboard
        (4 tabs, 15 visualizations, interactive Year filter)
```

---

##  Tech Stack

| Tool | Version | Purpose |
|------|---------|---------|
| **Metabase** | latest | Interactive dashboard & visualizations |
| **PostgreSQL** | 15 | Data storage, aggregation, materialized views |
| **Docker Compose** | - | One-command environment setup |
| **Python** | 3.12 | Data pipeline (ETL + cleaning) |
| **pandas** | 3.0+ | Data manipulation |
| **SQLAlchemy** | 2.0+ | Database connection |
| **requests** | - | Météo France API calls |
| **python-dotenv** | 1.2+ | Environment variables management |

---

##  Data Sources

| Source | Type | Coverage |
|--------|------|---------|
| Météo France Open Data | CSV (manual) | Département 01 — Ain |
| Météo France Open Data API | CSV.GZ (automatic) | Depts 06, 13, 33, 59, 67, 69, 75 |

**URL:** https://meteo.data.gouv.fr/datasets/6569b51ae64326786e4e8e1a

**Parameters collected:**

| Column | Description |
|--------|-------------|
| `temp_moyenne` | Daily average temperature (°C) |
| `temp_max` | Daily maximum temperature (°C) |
| `temp_min` | Daily minimum temperature (°C) |
| `precipitation` | Daily precipitation (mm) |
| `duree_gel` | Daily frost duration (minutes, T° < 0°C) |
| `vent_moyen` | Daily average wind speed (m/s) |
| `lat`, `lon`, `altitude` | Station coordinates |

**Total volume:** ~8.6 million rows | 1950–2024 | 831 weather stations

### Why 7 departments?

We selected 7 departments to maximize geographic and climatic diversity:

| Dept | City | Climate |
|------|------|---------|
| 01 | Ain | Continental (reference) |
| 06 | Nice | Mediterranean (hottest) |
| 13 | Marseille | Mediterranean South |
| 33 | Bordeaux | Atlantic (vineyards) |
| 59 | Lille | Northern oceanic |
| 67 | Strasbourg | Continental East |
| 69 | Lyon | Centre-East |
| 75 | Paris | National reference |

---

##  Getting Started

### Prerequisites
- Docker Desktop
- Python 3.8+
- Git

### 1. Clone the repository
```bash
git clone https://github.com/RayelenGuesmi/meteo-france-visualization.git
cd meteo-france-visualization
```

### 2. Configure environment variables
```bash
cp .env.example .env
# Edit .env with your credentials if needed
```

### 3. Start the infrastructure
```bash
docker-compose up -d
```

This starts:
- **PostgreSQL** on internal port 5432 (mapped to 5436 on host)
- **Metabase** on port 4200 → http://localhost:4200

### 4. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 5. Download department 01 data manually
Go to https://meteo.data.gouv.fr and download:
`Q_01_previous-1950-2024_RR-T-Vent.csv` → place in `data/`

### 6. Load all data
```bash
python scripts/load_meteo_data.py
```
Downloads 7 departments via API + loads local CSV.
Uses **COPY PostgreSQL** for fast insertion: **~3 minutes** for 8.6M rows.

### 7. Clean and standardize data
```bash
python scripts/clean_data.py
```
Applies quality checks and generates `rapport_qualite.txt`. Takes ~5 minutes.

### 8. Configure Metabase
Open http://localhost:4200, create an account, then add a PostgreSQL database:
- Host: `postgres`
- Port: `5432`
- Database: `meteo_france`
- Username: `meteo_user`
- Password: `meteo_pass`

---

##  Data Cleaning Details

The `clean_data.py` script applies the following steps:

| Step | Description | Result |
|------|-------------|--------|
| **Null removal** | Drop rows with no measurements at all | 24,154 removed |
| **Deduplication** | Remove exact duplicates on (station, date) | 0 removed |
| **Outlier detection** | Temp outside [-40°C, +50°C] → NULL | Physical limits |
| **Coherence check** | temp_min > temp_max → both set to NULL | 0 fixed |
| **Precipitation** | Negative or >500mm/day → NULL | 2 removed |
| **Wind speed** | Negative or >100 m/s → NULL | 0 removed |
| **Name standardization** | UPPER + TRIM | 831 stations |
| **Quality flag** | `complete` / `partial` per row | Added column |

**Final dataset:** 8,568,738 rows | 99.7% retained

A detailed quality report is automatically saved to `rapport_qualite.txt` after each run.

---

##  Performance Notes

### Data Loading Times (COPY PostgreSQL method)

| Step | Rows | Time |
|------|------|------|
| `load_meteo_data.py` — 8 departments | 8.6M | **~3 min** ✅ |
| `clean_data.py` — SQL native cleaning | 8.6M | **~5 min** ✅ |

> **Why so fast?** We use PostgreSQL's native `COPY` command instead of
> row-by-row `INSERT`. This loads data directly from a memory buffer,
> bypassing most of the overhead of standard SQL inserts.
> Result: **10x faster** than pandas `to_sql()`.

---

##  Dashboard

### Altitude Filter
All visualizations apply an **altitude < 500m filter** to exclude high-altitude mountain stations (Alps, Pyrenees) that would bias national temperature averages downward. This ensures we represent ground-level climate typical of populated areas.

### Visualizations (13 total)

**Tab 1 — Warming Story**
- Temperature Trend 1950–2024 (line chart)
- Station Temperatures Map (pin map)
- Annual Precipitation 1950–2024 (bar chart)
- Max Temperature Records 1950–2024 (line chart)

**Tab 2 — Regional Comparison**
- Summer Heat Map (pin map, months 6–8)
- Average Temperature by City (bar chart, top 20)
- Temperature Evolution by City (multi-series line chart)
- Temperature Map by Department (choropleth map) — uses GeoJSON
- Temperature Map by Region (choropleth map) — uses GeoJSON

**Tab 3 — Extreme Events**
- Frost Days per Year (line chart) — uses `duree_gel`
- Wind Speed Trend 1950–2024 (line chart) — uses `vent_moyen`
- Hot Days per Year >35°C (area chart)
- Monthly Temperature Heatmap (pivot table)
- Top 10 Hottest Years — Max Temp (table)

**Tab 4 — Precipitation**
- Precipitation Extremes 1950–2024 with drought line at 500mm (line chart)
- Precipitation by City (bar chart, top 10)
- Precipitation by Month (bar chart)

**Interactive filter:** Year selector connected to all tabs simultaneously.

---

### GeoJSON Maps

Two custom GeoJSON maps are configured in Metabase for choropleth visualizations:

| Map | URL | Field |
|-----|-----|-------|
| France Régions | https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/regions.geojson | code |
| France Départements | https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/departements.geojson | code |

Two SQL views map our data to these regions:
- `temp_par_region` — average temperature per region (6 regions covered)
- `temp_par_departement` — average temperature per department (8 departments covered)

##  Agile Methodology

Project managed using **SCRUM** over 5 weeks:

| Sprint | Goals |
|--------|-------|
| Sprint 1 | Data exploration & storytelling definition |
| Sprint 2 | Docker + PostgreSQL + Metabase setup |
| Sprint 3 | Data pipeline (load + clean) |
| Sprint 4 | Dashboard construction (4 tabs, 13 viz) |
| Sprint 5 | Presentation & final delivery |

---

##  Authors

- **Tharshan SIVAPALAN**
- **Rayelen GUESMI**

---

##  License

Open data from Météo France is licensed under [Licence Ouverte / Open Licence](https://www.etalab.gouv.fr/licence-ouverte-open-licence).