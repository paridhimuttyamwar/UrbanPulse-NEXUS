-- UrbanPulse Relational Database Schema
-- MySQL 8.0 Compatible

CREATE DATABASE IF NOT EXISTS urbanpulse
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE urbanpulse;

-- 1. Locations Table
CREATE TABLE IF NOT EXISTS locations (
    location_id VARCHAR(32) PRIMARY KEY,
    city_name VARCHAR(64) NOT NULL,
    state_name VARCHAR(64),
    country VARCHAR(64) NOT NULL DEFAULT 'India',
    latitude DECIMAL(9, 6) NOT NULL,
    longitude DECIMAL(9, 6) NOT NULL,
    timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Kolkata',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 2. Road Segments Table
CREATE TABLE IF NOT EXISTS road_segments (
    segment_id VARCHAR(32) PRIMARY KEY,
    location_id VARCHAR(32) NOT NULL,
    road_name VARCHAR(128) NOT NULL,
    segment_type ENUM('HIGHWAY', 'ARTERIAL', 'DOWNTOWN', 'SUBURBAN') NOT NULL DEFAULT 'ARTERIAL',
    speed_limit_kmh INT NOT NULL DEFAULT 50,
    length_km DECIMAL(5, 2) NOT NULL DEFAULT 2.0,
    capacity_vph INT NOT NULL DEFAULT 2000,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (location_id) REFERENCES locations(location_id) ON DELETE CASCADE,
    INDEX idx_segment_location (location_id)
) ENGINE=InnoDB;

-- 3. Traffic Sensors Table
CREATE TABLE IF NOT EXISTS traffic_sensors (
    sensor_id VARCHAR(32) PRIMARY KEY,
    segment_id VARCHAR(32) NOT NULL,
    sensor_name VARCHAR(64) NOT NULL,
    sensor_type VARCHAR(32) NOT NULL DEFAULT 'LOOP_DETECTOR',
    status ENUM('ACTIVE', 'INACTIVE', 'FAULTY') NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (segment_id) REFERENCES road_segments(segment_id) ON DELETE CASCADE,
    INDEX idx_sensor_segment (segment_id)
) ENGINE=InnoDB;

-- 4. Traffic Readings Table
CREATE TABLE IF NOT EXISTS traffic_readings (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(64) UNIQUE NOT NULL,
    sensor_id VARCHAR(32) NOT NULL,
    segment_id VARCHAR(32) NOT NULL,
    timestamp DATETIME NOT NULL,
    vehicle_count INT NOT NULL,
    avg_speed_kmh DECIMAL(5, 2) NOT NULL,
    congestion_level ENUM('LOW', 'MEDIUM', 'HIGH', 'SEVERE') NOT NULL,
    traffic_density_vpk DECIMAL(6, 2) NOT NULL,
    source_type VARCHAR(20) NOT NULL DEFAULT 'SIMULATED',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (segment_id) REFERENCES road_segments(segment_id) ON DELETE CASCADE,
    INDEX idx_traffic_timestamp (timestamp),
    INDEX idx_traffic_segment_time (segment_id, timestamp)
) ENGINE=InnoDB;

-- 5. Weather Readings Table
CREATE TABLE IF NOT EXISTS weather_readings (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(64) UNIQUE NOT NULL,
    location_id VARCHAR(32) NOT NULL,
    timestamp DATETIME NOT NULL,
    temperature_c DECIMAL(5, 2),
    relative_humidity_pct DECIMAL(5, 2),
    wind_speed_kmh DECIMAL(5, 2),
    precipitation_mm DECIMAL(5, 2),
    weather_condition VARCHAR(64),
    weather_code INT,
    source_type VARCHAR(20) NOT NULL DEFAULT 'REAL_API',
    measurement_type VARCHAR(32) NOT NULL DEFAULT 'OBSERVED_API',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (location_id) REFERENCES locations(location_id) ON DELETE CASCADE,
    INDEX idx_weather_timestamp (timestamp),
    INDEX idx_weather_location_time (location_id, timestamp)
) ENGINE=InnoDB;

-- 6. Air Quality Readings Table
CREATE TABLE IF NOT EXISTS air_quality_readings (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(64) UNIQUE NOT NULL,
    location_id VARCHAR(32) NOT NULL,
    timestamp DATETIME NOT NULL,
    pm2_5 DECIMAL(6, 2),
    pm10 DECIMAL(6, 2),
    nitrogen_dioxide DECIMAL(6, 2),
    ozone DECIMAL(6, 2),
    carbon_monoxide DECIMAL(6, 2),
    us_aqi INT,
    european_aqi INT,
    aqi_category VARCHAR(32),
    source_type VARCHAR(20) NOT NULL DEFAULT 'REAL_API',
    measurement_type VARCHAR(32) NOT NULL DEFAULT 'OBSERVED_OR_MODELED_API',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (location_id) REFERENCES locations(location_id) ON DELETE CASCADE,
    INDEX idx_aq_timestamp (timestamp),
    INDEX idx_aq_location_time (location_id, timestamp)
) ENGINE=InnoDB;

-- 7. IoT Devices Table
CREATE TABLE IF NOT EXISTS iot_devices (
    device_id VARCHAR(32) PRIMARY KEY,
    device_name VARCHAR(64) NOT NULL,
    device_model VARCHAR(64) NOT NULL DEFAULT 'Arduino Uno R3',
    device_type VARCHAR(20) NOT NULL DEFAULT 'PHYSICAL',
    location_id VARCHAR(32),
    connected_sensors VARCHAR(255) DEFAULT 'DHT11,MQ-135,LDR',
    port_assignment VARCHAR(32) DEFAULT NULL,
    status ENUM('ONLINE', 'OFFLINE', 'ERROR') NOT NULL DEFAULT 'OFFLINE',
    last_heartbeat DATETIME,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (location_id) REFERENCES locations(location_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- 8. IoT Sensor Readings Table
CREATE TABLE IF NOT EXISTS iot_sensor_readings (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(64) UNIQUE NOT NULL,
    device_id VARCHAR(32) NOT NULL,
    sensor_type VARCHAR(32) NOT NULL,
    reading_value DECIMAL(8, 2) NOT NULL,
    unit VARCHAR(16) NOT NULL,
    timestamp DATETIME NOT NULL,
    raw_reading_text VARCHAR(255),
    source_type VARCHAR(20) NOT NULL DEFAULT 'REAL_HARDWARE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES iot_devices(device_id) ON DELETE CASCADE,
    INDEX idx_iot_timestamp (timestamp),
    INDEX idx_iot_device_time (device_id, timestamp)
) ENGINE=InnoDB;

-- 9. Anomalies Table
CREATE TABLE IF NOT EXISTS anomalies (
    anomaly_id VARCHAR(64) PRIMARY KEY,
    anomaly_type VARCHAR(64) NOT NULL,
    source_type VARCHAR(32) NOT NULL,
    location_id VARCHAR(32),
    segment_id VARCHAR(32),
    timestamp DATETIME NOT NULL,
    severity ENUM('LOW', 'MEDIUM', 'HIGH', 'CRITICAL') NOT NULL,
    description TEXT NOT NULL,
    status ENUM('ACTIVE', 'RESOLVED', 'ACKNOWLEDGED') NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_anomaly_status (status),
    INDEX idx_anomaly_time (timestamp)
) ENGINE=InnoDB;

-- 10. Hourly Traffic Metrics Table (Aggregated)
CREATE TABLE IF NOT EXISTS hourly_traffic_metrics (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    segment_id VARCHAR(32) NOT NULL,
    hour_bucket DATETIME NOT NULL,
    avg_vehicle_count DECIMAL(7, 2) NOT NULL,
    avg_speed_kmh DECIMAL(5, 2) NOT NULL,
    peak_vehicle_count INT NOT NULL,
    congestion_index DECIMAL(5, 2) NOT NULL,
    sample_count INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_segment_hour (segment_id, hour_bucket),
    INDEX idx_htm_hour (hour_bucket)
) ENGINE=InnoDB;

-- 11. Daily Environment Metrics Table (Aggregated)
CREATE TABLE IF NOT EXISTS daily_environment_metrics (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    location_id VARCHAR(32) NOT NULL,
    date_bucket DATE NOT NULL,
    avg_temperature_c DECIMAL(5, 2),
    min_temperature_c DECIMAL(5, 2),
    max_temperature_c DECIMAL(5, 2),
    avg_humidity_pct DECIMAL(5, 2),
    total_precipitation_mm DECIMAL(5, 2),
    avg_pm2_5 DECIMAL(6, 2),
    avg_pm10 DECIMAL(6, 2),
    max_aqi INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_location_date (location_id, date_bucket),
    INDEX idx_dem_date (date_bucket)
) ENGINE=InnoDB;

-- 12. Pipeline Runs Table
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id VARCHAR(64) PRIMARY KEY,
    pipeline_name VARCHAR(64) NOT NULL,
    status ENUM('STARTED', 'SUCCESS', 'FAILED') NOT NULL,
    records_processed INT DEFAULT 0,
    records_rejected INT DEFAULT 0,
    started_at DATETIME NOT NULL,
    finished_at DATETIME,
    error_message TEXT
) ENGINE=InnoDB;

-- 13. Rejected Records Table
CREATE TABLE IF NOT EXISTS rejected_records (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(64),
    source_name VARCHAR(64) NOT NULL,
    source_type VARCHAR(32) NOT NULL,
    raw_payload LONGTEXT NOT NULL,
    rejection_reason TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_rejected_source (source_name),
    INDEX idx_rejected_timestamp (timestamp)
) ENGINE=InnoDB;
