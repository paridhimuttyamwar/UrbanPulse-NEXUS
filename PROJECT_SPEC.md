# UrbanPulse — System Specification

## 1. Overview
UrbanPulse is a smart-city data engineering and real-time urban intelligence platform designed for Windows 11 (12 GB RAM) environments. It integrates real weather data (Open-Meteo), real air-quality data (Open-Meteo Air Quality API), realistic simulated urban traffic data, and hardware-collected IoT sensor data (Arduino Uno R3 via USB PySerial).

## 2. Core Architecture
- **Dual Pipeline Architecture**:
  1. **Streaming Pipeline**: Simulated traffic events & Arduino IoT serial readings -> Kafka topics (`urbanpulse.traffic.raw`, `urbanpulse.iot.raw`) -> Python Kafka Consumer -> Validation -> Idempotent MySQL insertion -> Streamlit dashboard.
  2. **Batch Pipeline**: Open-Meteo APIs (Weather, Air Quality) -> Extraction -> Local Raw JSONL archival -> Validation -> Idempotent MySQL insertion -> Scheduled via Airflow / CLI.
- **Relational Database**: MySQL Community Edition 8.0 (running locally on port 3306).
- **Data Labeling / Source Attribution**: Every record carries an explicit `source_type` (`REAL_API`, `REAL_HARDWARE`, `SIMULATED`) and `measurement_type`.
- **Fault-Tolerant Validation**: Reusable validation modules reject invalid/malformed records into `data/rejected/` and the `rejected_records` table with detailed reasons.

## 3. Technology Stack
- **Language**: Python 3.13
- **Data Processing**: Pandas, NumPy
- **Database**: MySQL 8.0 (`mysql-connector-python`)
- **Streaming**: Apache Kafka (KRaft mode via Docker Compose)
- **Orchestration**: Apache Airflow
- **Visualization**: Streamlit, Plotly
- **Hardware Integration**: Arduino Uno R3, PySerial
- **Storage**: Local JSON Lines archival (`data/raw/`, `data/processed/`, `data/rejected/`) with future S3 compatibility.

## 4. Development Constraints & Principles
- Memory footprint tuned for 12 GB RAM laptop.
- Subsystems run and test independently without requiring all services active simultaneously.
- No spark/hadoop/kubernetes/mongodb/redshift overhead.
- Idempotent database writes and at-least-once streaming processing.
