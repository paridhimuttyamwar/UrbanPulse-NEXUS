# UrbanPulse — Interview Preparation & Technical Deep-Dive

## 1. The 60-Second Elevator Pitch
> *"UrbanPulse is an end-to-end Smart City Data Engineering platform that collects, validates, aggregates, and visualizes urban mobility, atmospheric, and edge IoT data. It employs a decoupled dual-pipeline architecture: near-real-time streaming via Apache Kafka and PySerial for traffic and microcontrollers, alongside scheduled batch ingestion via Open-Meteo APIs and Apache Airflow. The system emphasizes data provenance—strictly distinguishing between live API measurements, Greenshields-modeled traffic simulations, and Arduino Uno R3 hardware telemetry. It provides idempotent MySQL persistence, dead-letter rejection tracking, rule-based anomaly detection, and an interactive Streamlit operations dashboard."*

---

## 2. Key Architecture Decisions & Rationales

### Q1: Why use a Dual-Pipeline (Lambda-style) instead of running everything through Kafka or Airflow?
**Answer:**
- **Kafka for Streaming:** Traffic flows and microcontroller readings arrive continuously at high frequencies. Putting them through a batch scheduler like Airflow would incur unacceptable latency and task scheduling overhead.
- **Airflow for Batch:** Weather and municipal air quality models publish updates once every 1–3 hours. Pushing these slow-moving API calls through continuous Kafka streams adds architectural bloat. Airflow provides bounded retries, task dependencies, and scheduled cron orchestration suited for batch ETL.
- **Separation of Concerns:** Each pipeline is tailored to the velocity, volume, and latency characteristics of its data source.

### Q2: Why MySQL Community Edition instead of PostgreSQL or MongoDB?
**Answer:**
- **Relational Integrity:** Smart city topology is relational: cities contain road segments; road segments contain sensors; sensors emit readings. Foreign keys, cascading constraints, and relational joins prevent orphaned records.
- **Idempotency with `ON DUPLICATE KEY UPDATE`:** MySQL allows deterministic event IDs to serve as unique keys, guaranteeing idempotent writes during consumer replays or network retries.
- **Resource Footprint:** MySQL 8.0 operates with low memory overhead on a 12 GB RAM development environment, whereas large document stores or distributed clusters incur unnecessary overhead.

### Q3: Why KRaft mode for Kafka instead of ZooKeeper?
**Answer:**
- ZooKeeper requires a second JVM process, doubling memory footprint and configuration complexity.
- KRaft (Kafka Raft Metadata mode) consolidates broker and controller roles into a single lightweight JVM process capped at 512 MB heap, ideal for resource-constrained local development.

### Q4: How does your streaming consumer guarantee At-Least-Once delivery?
**Answer:**
1. Consumer configuration sets `enable_auto_commit=False`.
2. Message payload is pulled from Kafka and validated against Pydantic models.
3. Record is written to MySQL using `ON DUPLICATE KEY UPDATE` (idempotent upsert).
4. Raw payload is archived to JSON Lines.
5. Only after the database commit succeeds does the consumer call `consumer.commit()`.
6. If the consumer crashes prior to commit, the message is re-consumed upon restart; because writes are idempotent, duplicates do not corrupt the database.

### Q5: How do you handle malformed or out-of-range sensor readings?
**Answer:**
- We enforce a **Zero Silent Drops** policy.
- Payloads are validated against Pydantic schemas checking types, timestamps, and physical plausibility (e.g. speed $\le$ 200 km/h, vehicle count $\ge$ 0, humidity $\in [0, 100]$).
- Invalid payloads are redirected to a dead-letter quarantine: both written to `data/rejected/` JSONL and logged in the `rejected_records` table with the exact validation failure message and raw payload.

### Q6: How does the Arduino Uno R3 integrate, and what are its scientific limitations?
**Answer:**
- The Arduino Uno R3 runs embedded C/C++ firmware that reads sensors and transmits structured packets (`UP_IOT,DEVICE_ID,SENSOR,VALUE,UNIT,STATUS`) over USB serial at 9600 baud.
- A Python `PySerial` gateway reads the port, validates packets, attaches metadata (`REAL_HARDWARE`), and stores readings in MySQL.
- **Scientific Disclaimers:**
  - A DHT11 measures temperature and humidity, **not** air quality.
  - An MQ-135 produces a raw analog voltage (ADC 0-1023), which represents general chemical resistance and cannot be presented as official AQI or certified PM2.5.
  - The gateway employs exponential backoff: if the Arduino is disconnected, the platform continues operating with zero interruptions.

---

## 3. Top Resume Bullet Points for Placements

- **Engineered UrbanPulse**, an end-to-end smart city data engineering platform consolidating live Open-Meteo APIs, Greenshields traffic simulations, and Arduino Uno R3 IoT hardware telemetry.
- **Designed dual-pipeline architecture** combining an Apache Kafka streaming pipeline (at-least-once delivery, manual offset commits) with Apache Airflow batch workflows for scheduled API extraction and rollups.
- **Implemented normalized MySQL 8.0 schema** with 13 tables, composite indexes for sub-second analytical queries, and deterministic upserts (`ON DUPLICATE KEY UPDATE`) for idempotent ingestion.
- **Built Pydantic validation and dead-letter quarantine**, eliminating silent drops by archiving invalid payloads to JSON Lines and a dedicated audit table with field-level rejection reasons.
- **Engineered rule-based anomaly detection engine** monitoring multi-sensor thresholds to flag traffic gridlocks, hazardous US AQI levels, and hardware telemetry faults in near real time.
- **Developed multi-view Streamlit & Plotly analytics dashboard**, incorporating memory-cached query layers (`@st.cache_data`), EPA AQI gauges, and cross-domain correlation matrices with scientific provenance badges (`REAL_API`, `SIMULATED`, `REAL_HARDWARE`).
