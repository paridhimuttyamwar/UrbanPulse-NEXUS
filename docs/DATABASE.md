# UrbanPulse — Database Design & Schema Guide

## 1. Relational Database Overview
UrbanPulse employs **MySQL Community Edition 8.0** configured with the InnoDB storage engine and `utf8mb4` encoding.

### Entity Relationship Model

```
locations (1) ──< road_segments (N) ──< traffic_sensors (N) ──< traffic_readings (N)
   │
   ├──< weather_readings (N)
   ├──< air_quality_readings (N)
   └──< iot_devices (N) ──< iot_sensor_readings (N)

anomalies (Stand-alone incident log)
hourly_traffic_metrics (Aggregated rollup)
daily_environment_metrics (Aggregated rollup)
pipeline_runs (ETL Telemetry)
rejected_records (Data Quality & Dead-Letter Log)
```

---

## 2. Table Specifications

### Core Domain Tables
1. **`locations`**: Defines municipal boundaries and geographical centroids (latitude, longitude).
2. **`road_segments`**: Defines individual urban corridors, speed limits, lengths, and vehicular capacities.
3. **`traffic_sensors`**: Physical detector units (Loop Detectors, Radars) mapped to road segments.
4. **`traffic_readings`**: High-frequency mobility observations containing vehicle count, average speed, congestion level, and traffic density.
5. **`weather_readings`**: Ambient conditions (temperature, humidity, wind, precipitation, WMO condition).
6. **`air_quality_readings`**: Atmospheric chemical levels (PM2.5, PM10, NO2, O3, CO) and EPA US AQI categories.
7. **`iot_devices`**: Edge hardware registry tracking device status and last heartbeat timestamp.
8. **`iot_sensor_readings`**: Time-series sensor logs received from Arduino microcontrollers.

### Analytics & Governance Tables
9. **`hourly_traffic_metrics`**: Pre-aggregated hourly rollups (mean volume, speed, peak count, congestion index). Unique key on `(segment_id, hour_bucket)`.
10. **`daily_environment_metrics`**: Daily environmental rollups per location. Unique key on `(location_id, date_bucket)`.
11. **`anomalies`**: Rule-based alerts flagged across traffic, air quality, or sensors with status (`ACTIVE`, `ACKNOWLEDGED`, `RESOLVED`).
12. **`pipeline_runs`**: Audit log of batch ETL runs, record counts, execution duration, and error traces.
13. **`rejected_records`**: Dead-letter record repository storing unparseable or out-of-bounds payloads alongside the exact rejection reason.

---

## 3. High-Throughput Time-Series Indexing

To ensure Streamlit dashboards load sub-second even with millions of rows, composite indexes are placed along query axes:
- `idx_traffic_segment_time (segment_id, timestamp)`
- `idx_weather_location_time (location_id, timestamp)`
- `idx_aq_location_time (location_id, timestamp)`
- `idx_htm_hour (hour_bucket)`
- `idx_dem_date (date_bucket)`

---

## 4. Idempotent Write Strategy

All pipeline writes use deterministic event IDs (`EVT_...`) combined with `ON DUPLICATE KEY UPDATE`:
```sql
INSERT INTO weather_readings (event_id, location_id, timestamp, temperature_c, ...)
VALUES (...)
ON DUPLICATE KEY UPDATE
    temperature_c = VALUES(temperature_c),
    ...;
```
This guarantees that pipeline retries, replay of raw JSONL files, or consumer restarts never produce duplicate rows.
