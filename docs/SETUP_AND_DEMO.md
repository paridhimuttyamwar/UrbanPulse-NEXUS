# UrbanPulse NEXUS — Local Setup & Live Demonstration Guide
### Optimized for Windows 11 (12 GB RAM) Environment

This guide provides step-by-step instructions to set up, initialize, run, and demonstrate **UrbanPulse NEXUS** locally. It includes an interactive live demonstration script suitable for technical interviews and project evaluations.

---

## 1. System Requirements & Prerequisites

| Requirement | Supported Version | Notes |
| :--- | :--- | :--- |
| **Operating System** | Windows 10 / Windows 11 | Tested on Windows 11 Home/Pro |
| **Python** | 3.11, 3.12, or 3.13 | Ensure Python is added to host `PATH` |
| **Database** | MySQL Server 8.0 Community | Running locally on port `3306` |
| **RAM** | Minimum 8 GB (Recommended: 12 GB) | Optimized via standalone batch runner |
| **Storage** | 2 GB free disk space | Required for dependencies, raw JSONL, and MySQL tables |
| **Optional Services** | Docker Desktop & Apache Kafka | Not required for base operation (fallback active) |

---

## 2. Environment Configuration & Setup

### Step 2.1: Clone and Navigate to Project
Open Windows PowerShell (Run as Administrator or standard user):
```powershell
cd C:\Users\Dell\.gemini\antigravity\scratch\urbanpulse
```

### Step 2.2: Create and Activate Virtual Environment
```powershell
# Create virtual environment
python -m venv .venv

# Set execution policy if script activation is restricted
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# Activate virtual environment
.venv\Scripts\Activate.ps1
```

### Step 2.3: Install Pinned Dependencies
```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2.4: Configure Environment Variables
Copy the template and verify credentials:
```powershell
Copy-Item .env.example .env
```
Open `.env` in Notepad or your editor and adjust your MySQL password:
```ini
# Database Credentials
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=urbanpulse

# Streaming & Gateway
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TRAFFIC_TOPIC=urbanpulse.traffic.raw
ARDUINO_PORT=COM3
ARDUINO_BAUD_RATE=9600

# Open-Meteo REST API
OPEN_METEO_BASE_URL=https://api.open-meteo.com/v1/forecast
OPEN_METEO_AQ_BASE_URL=https://air-quality-api.open-meteo.com/v1/air-quality
API_TIMEOUT_SECONDS=10
API_MAX_RETRIES=3

# Storage Directories
RAW_DATA_DIR=data/raw
PROCESSED_DATA_DIR=data/processed
REJECTED_DATA_DIR=data/rejected
```

---

## 3. Database Initialization

Execute the database provisioning script to create the schema, 13 tables, primary/foreign keys, composite indexes, and seed initial metadata for Nagpur:
```powershell
python database\init_db.py
```
**Expected Output:**
```text
Executing database/schema.sql...
Schema created successfully.
Executing database/seed_data.sql...
Seed data inserted successfully.
UrbanPulse database initialized with 13 core tables.
```

---

## 4. Launching the Platform

### Step 4.1: Launch Streamlit Operations Center
In your primary terminal:
```powershell
streamlit run dashboard\app.py
```
The dashboard will open automatically in your default web browser at **`http://localhost:8501`**.

---

## 5. Live Demonstration Script (Step-by-Step)

Follow this structured workflow during a live project evaluation:

### Step 1: Overview Command Center (`Overview` page)
1. Navigate to **`🏙️ Overview`** via the sidebar navigation.
2. Highlight the **Nagpur Smart City** operational scope:
   - Point out the 3 atmospheric nodes (Ramdaspeth, Sitabuldi, Civil Lines).
   - Show the citywide KPI metrics (Citywide Average Speed, Active Anomalies, Registered Lab Nodes).
3. Expand **`🛠️ System Diagnostics & Operational Telemetry`**:
   - Point out the **Database Tier**: `🟢 Operational (Connected)` via the connection pool.
   - Point out the **Streaming & Broker**: `⚪ Standby (Offline simulation mode)` — explaining that the architecture gracefully operates in fallback mode without requiring heavy Docker containers.
   - Point out the **Edge Sensing Lab**: `⚪ Standby (Virtual Gateway Active)` — showing truthful hardware port detection.

### Step 2: Live Real-Time API Synchronization (`Environmental Monitoring` page)
1. Navigate to **`🌤️ Environmental Monitoring`**.
2. Note the Open-Meteo observation timestamp and US-EPA AQI radial gauge.
3. Scroll down and click the **`🔄 Synchronize Live Open-Meteo Observations Now`** button.
4. **Observe:** The client calls the live Open-Meteo REST API, validates the weather and AQI payloads with Pydantic, inserts them into MySQL (`weather_readings`, `air_quality_readings`), clears Streamlit caches, and refreshes the gauges in real time.

### Step 3: Corridor Mobility Analytics (`Traffic Intelligence` page)
1. Navigate to **`🚦 Traffic Intelligence`**.
2. Explain the **Greenshields Traffic Model**:
   - Select corridors such as `Wardha Road (Airport Corridor)` or `Central Avenue (Commercial Spine)`.
   - Show the dynamic speed distribution and congestion categorization (`LOW`, `MEDIUM`, `HIGH`, `SEVERE`).
3. Demonstrate **Historical Date Filtering**:
   - Change the date filter to observe dynamic aggregation without database crashes.

### Step 4: Cross-Domain Correlation Analysis (`Urban Analytics` page)
1. Navigate to **`📈 Urban Analytics`**.
2. Explain the **Cross-Domain Correlation Matrix**:
   - Show how traffic velocities correlate with atmospheric factors.
   - Highlight the **Temporal Alignment**: Explain how UTC traffic timestamps are shifted $+330$ minutes to match IST local weather readings into hourly buckets.
   - Show the **Methodological Safeguard**: If environmental observation variance is zero, the engine displays a traffic-only matrix with an explicit disclaimer rather than replacing `NaN` with zeros.

### Step 5: Edge IoT Lab & Dual-Mode Telemetry (`Edge IoT Lab` page)
1. Navigate to **`🔌 Edge IoT Lab`**.
2. Point out the **Registered Lab Nodes** card (`Arduino Uno — Local Lab`).
3. Under **Operational Edge Ingestion Modes**, select **`⚡ Mode A: Virtual Sensor Simulator`**:
   - Select sensor type: `DHT11_TEMP`.
   - Enter reading: `31.5` °C.
   - Click **`Transmit Packet via Virtual Gateway`**.
   - **Observe:** Green success banner appears; raw payload archived; MySQL record inserted; device status transitions to **`STREAMING`** / **`CONNECTED`**; chart refreshes immediately.
4. Switch to **`🔌 Mode B: Physical Arduino Connection (USB)`**:
   - Point out the truthful serial port probe (`⚪ DISCONNECTED - COM3 not found on host`).
   - Click **`🔍 Probe Host Serial Ports Now`** to verify live hardware scanning.

### Step 6: Incident Triage Console (`Anomaly Center` page)
1. Navigate to **`🚨 Anomaly Center`**.
2. Observe active incidents generated by speed drops or extreme sensor thresholds.
3. Select an active incident and click **`Acknowledge`**:
   - Status updates from **`ACTIVE`** $\to$ **`ACKNOWLEDGED`**.
4. Click **`Resolve Incident`**:
   - Status updates to **`RESOLVED`**.
5. Explain the **60-Minute Cooldown Mechanism**: Identical abnormal readings within the last 60 minutes are suppressed to eliminate alert fatigue.

---

## 6. Standalone Batch Runner (Airflow DAG Workflows)

To test scheduled batch rollups on a 12 GB RAM machine without running heavy Docker daemons:
```powershell
# Run all batch workflows
python airflow\run_pipeline.py all

# Run specific workflows
python airflow\run_pipeline.py weather
python airflow\run_pipeline.py air_quality
python airflow\run_pipeline.py traffic_metrics
python airflow\run_pipeline.py environment_metrics
python airflow\run_pipeline.py data_quality
```

---

## 7. Troubleshooting & FAQ

| Problem | Root Cause | Solution |
| :--- | :--- | :--- |
| **`Access denied for user 'root'@'localhost'`** | Incorrect password in `.env` | Update `MYSQL_PASSWORD` in `.env` to match your local MySQL root password. |
| **Port 8501 already in use** | An existing Streamlit instance is running | Run on an alternative port: `streamlit run dashboard\app.py --server.port 8502` |
| **`No module named 'config'`** | Working directory is incorrect or virtual environment inactive | Ensure you are in the project root directory and `.venv` is activated. |
| **Serial Gateway reports Port Closed** | No Arduino is connected to COM3 | This is expected behavior. The platform automatically uses Mode A (Virtual Gateway) with zero data loss. |
| **Kafka Connection Error** | Kafka broker is not started | This is expected in standalone mode. Producers and consumers operate in fallback mode with local disk archival. |
