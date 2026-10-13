-- Migration 002: IoT Telemetry Mode Separation & Provenance Isolation
-- Adds device_type, connected_sensors, and port_assignment to iot_devices
-- Quarantines unverified legacy readings and marks existing prototype nodes as VIRTUAL

-- 1. Add device_type column if not exists
ALTER TABLE iot_devices 
    ADD COLUMN IF NOT EXISTS device_type VARCHAR(20) NOT NULL DEFAULT 'PHYSICAL',
    ADD COLUMN IF NOT EXISTS connected_sensors VARCHAR(255) DEFAULT 'DHT11,MQ-135,LDR',
    ADD COLUMN IF NOT EXISTS port_assignment VARCHAR(32) DEFAULT NULL;

-- 2. Mark existing simulated prototype nodes as VIRTUAL
UPDATE iot_devices 
SET device_type = 'VIRTUAL', 
    device_name = 'Nagpur Zero Mile Edge Unit (Simulated)',
    connected_sensors = 'DHT11,MQ-135,LDR'
WHERE device_id = 'ARDUINO_UNO_NAG_01';

UPDATE iot_devices 
SET device_type = 'VIRTUAL', 
    device_name = 'UrbanPulse Edge Unit 1 (Virtual Prototype)',
    connected_sensors = 'DHT11,MQ-135,LDR'
WHERE device_id = 'ARDUINO_UNO_01';

-- 3. Quarantine unverified legacy test readings so they do not contaminate real hardware mode
UPDATE iot_sensor_readings 
SET source_type = 'UNVERIFIED_LEGACY' 
WHERE id IN (1, 2, 3, 4, 5) AND source_type = 'REAL_HARDWARE';
