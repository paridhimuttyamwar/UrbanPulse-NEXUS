# UrbanPulse — Developer & Operations Guide

## 1. System Requirements & Prerequisites
- **Operating System:** Windows 11 (or 10)
- **RAM:** 12 GB RAM
- **Python:** Version 3.11 – 3.13
- **Database:** Local MySQL Community Server 8.0 (Service `MySQL80`)
- **Hardware (Optional):** Arduino Uno R3 with USB cable
- **Container Engine (Optional):** Docker Desktop with Docker Compose

---

## 2. Setup & Installation

### Step 1: Clone & Configure Environment
```powershell
cd C:\Users\Dell\.gemini\antigravity\scratch\urbanpulse

# Copy template to .env and review database credentials
copy .env.example .env
```

Ensure your `.env` contains your local MySQL password:
```ini
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=root123
MYSQL_DATABASE=urbanpulse
```

### Step 2: Install Python Dependencies
```powershell
pip install -r requirements.txt
```

### Step 3: Initialize MySQL Database
```powershell
python database\init_db.py
```
*Creates the `urbanpulse` database, all 13 tables, and seeds 4 municipal locations, 15 road segments, and 15 traffic sensors.*

---

## 3. Subsystem Execution Commands

All subsystems can be run independently without starting heavy background containers:

### A. Run Batch Ingestion & Aggregations
```powershell
# Ingest live weather, air quality, compute traffic rollups, and audit quality:
python airflow\run_pipeline.py all

# Run specific single task:
python airflow\run_pipeline.py weather
python airflow\run_pipeline.py air_quality
python airflow\run_pipeline.py traffic_metrics
```

### B. Run Traffic Streaming Producer
```powershell
# Runs traffic simulator and streams events:
python streaming\producers\traffic_producer.py
```

### C. Run Traffic Streaming Consumer
```powershell
# Consumes and processes incoming events:
python streaming\consumers\traffic_consumer.py
```

### D. Launch Streamlit Operations Dashboard
```powershell
# Opens interactive dashboard in your default browser (localhost:8501):
streamlit run dashboard\app.py
```

### E. Run Arduino PySerial Gateway (Optional Hardware)
```powershell
# With Arduino Uno plugged into USB:
python iot\serial_gateway\gateway.py
```

---

## 4. Docker Subsystems (Optional / Resource Capped)

When you want to run Apache Kafka or Apache Airflow inside Docker containers:

```powershell
# Start Kafka KRaft broker independently:
docker compose --profile kafka up -d

# Stop Kafka broker:
docker compose --profile kafka down

# Start Apache Airflow Webserver & Scheduler:
docker compose --profile airflow up -d

# Stop Apache Airflow:
docker compose --profile airflow down
```

---

## 5. Verification & Testing
```powershell
# Verify Batch 1: DB connection, Open-Meteo APIs, and simulator validation
python tests\verify_batch1.py

# Verify Batch 2: Streaming pipeline, anomaly engine, rollups, and batch runner
python tests\verify_batch2.py

# Verify Batch 3: Dashboard data loader queries, view integrity, and compilation
python tests\verify_batch3.py

# Run full project integration test
python tests\verify_integration.py
```
