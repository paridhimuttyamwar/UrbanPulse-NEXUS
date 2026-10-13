-- UrbanPulse Database Migration 001: Add Nagpur Urban Network
-- Target Database: urbanpulse (MySQL 8.0)
-- Purpose: Adds Nagpur (LOC_NAGPUR) as the primary smart city topology, including
--          15 key urban corridors, 15 dedicated traffic sensors, and an edge IoT device.
-- Safety Guarantee: Non-destructive, idempotent (INSERT ... ON DUPLICATE KEY UPDATE).
--                   Preserves all historical records for Pune, Mumbai, Bengaluru, and Delhi.

USE urbanpulse;

-- 1. Register Nagpur Municipal Location
INSERT INTO locations (
    location_id, city_name, state_name, country, latitude, longitude, timezone
) VALUES (
    'LOC_NAGPUR', 'Nagpur', 'Maharashtra', 'India', 21.145800, 79.088200, 'Asia/Kolkata'
)
ON DUPLICATE KEY UPDATE
    city_name = VALUES(city_name),
    state_name = VALUES(state_name),
    country = VALUES(country),
    latitude = VALUES(latitude),
    longitude = VALUES(longitude),
    timezone = VALUES(timezone);

-- 2. Register 15 Nagpur Road Segments / Urban Corridors
INSERT INTO road_segments (
    segment_id, location_id, road_name, segment_type, speed_limit_kmh, length_km, capacity_vph
) VALUES
('SEG_NAG_01', 'LOC_NAGPUR', 'Wardha Road - Airport Corridor', 'HIGHWAY', 70, 6.00, 4500),
('SEG_NAG_02', 'LOC_NAGPUR', 'Sitabuldi Main Road', 'DOWNTOWN', 35, 1.80, 2000),
('SEG_NAG_03', 'LOC_NAGPUR', 'Dharampeth - Shankar Nagar Road', 'ARTERIAL', 45, 2.50, 2600),
('SEG_NAG_04', 'LOC_NAGPUR', 'Sadar Main Road', 'DOWNTOWN', 35, 2.00, 2100),
('SEG_NAG_05', 'LOC_NAGPUR', 'Manish Nagar Main Road', 'ARTERIAL', 40, 3.00, 2400),
('SEG_NAG_06', 'LOC_NAGPUR', 'Hingna Road', 'ARTERIAL', 50, 4.50, 3000),
('SEG_NAG_07', 'LOC_NAGPUR', 'Amravati Road', 'HIGHWAY', 65, 5.50, 4000),
('SEG_NAG_08', 'LOC_NAGPUR', 'Kamptee Road', 'HIGHWAY', 65, 5.00, 4000),
('SEG_NAG_09', 'LOC_NAGPUR', 'Central Avenue Road', 'ARTERIAL', 45, 4.00, 2800),
('SEG_NAG_10', 'LOC_NAGPUR', 'Medical Square - Ajni Road', 'ARTERIAL', 40, 3.20, 2500),
('SEG_NAG_11', 'LOC_NAGPUR', 'Trimurti Nagar Main Road', 'SUBURBAN', 40, 2.80, 2000),
('SEG_NAG_12', 'LOC_NAGPUR', 'Nandanvan Main Road', 'SUBURBAN', 40, 2.60, 1900),
('SEG_NAG_13', 'LOC_NAGPUR', 'MIHAN Access Road', 'HIGHWAY', 70, 5.00, 3800),
('SEG_NAG_14', 'LOC_NAGPUR', 'Civil Lines Road', 'DOWNTOWN', 40, 2.20, 2200),
('SEG_NAG_15', 'LOC_NAGPUR', 'Ring Road - Narendra Nagar Corridor', 'HIGHWAY', 65, 6.50, 4200)
ON DUPLICATE KEY UPDATE
    road_name = VALUES(road_name),
    segment_type = VALUES(segment_type),
    speed_limit_kmh = VALUES(speed_limit_kmh),
    length_km = VALUES(length_km),
    capacity_vph = VALUES(capacity_vph);

-- 3. Register 15 Traffic Flow Monitoring Sensors
INSERT INTO traffic_sensors (
    sensor_id, segment_id, sensor_name, sensor_type, status
) VALUES
('SNS_TRF_NAG_01', 'SEG_NAG_01', 'Wardha Rd Gantry Radar 01', 'RADAR', 'ACTIVE'),
('SNS_TRF_NAG_02', 'SEG_NAG_02', 'Sitabuldi Interchange Loop 02', 'LOOP_DETECTOR', 'ACTIVE'),
('SNS_TRF_NAG_03', 'SEG_NAG_03', 'Dharampeth Junction Loop 03', 'LOOP_DETECTOR', 'ACTIVE'),
('SNS_TRF_NAG_04', 'SEG_NAG_04', 'Sadar Market Flow Radar 04', 'RADAR', 'ACTIVE'),
('SNS_TRF_NAG_05', 'SEG_NAG_05', 'Manish Nagar Crossing Loop 05', 'LOOP_DETECTOR', 'ACTIVE'),
('SNS_TRF_NAG_06', 'SEG_NAG_06', 'Hingna MIDC Approach Loop 06', 'LOOP_DETECTOR', 'ACTIVE'),
('SNS_TRF_NAG_07', 'SEG_NAG_07', 'Amravati Rd Highway Radar 07', 'RADAR', 'ACTIVE'),
('SNS_TRF_NAG_08', 'SEG_NAG_08', 'Kamptee Rd Flyover Radar 08', 'RADAR', 'ACTIVE'),
('SNS_TRF_NAG_09', 'SEG_NAG_09', 'CA Road Commercial Loop 09', 'LOOP_DETECTOR', 'ACTIVE'),
('SNS_TRF_NAG_10', 'SEG_NAG_10', 'Medical Square Camera Radar 10', 'RADAR', 'ACTIVE'),
('SNS_TRF_NAG_11', 'SEG_NAG_11', 'Trimurti Nagar Colony Loop 11', 'LOOP_DETECTOR', 'ACTIVE'),
('SNS_TRF_NAG_12', 'SEG_NAG_12', 'Nandanvan Transit Loop 12', 'LOOP_DETECTOR', 'ACTIVE'),
('SNS_TRF_NAG_13', 'SEG_NAG_13', 'MIHAN SEZ Expressway Radar 13', 'RADAR', 'ACTIVE'),
('SNS_TRF_NAG_14', 'SEG_NAG_14', 'Civil Lines Secretariat Loop 14', 'LOOP_DETECTOR', 'ACTIVE'),
('SNS_TRF_NAG_15', 'SEG_NAG_15', 'Narendra Nagar Ring Radar 15', 'RADAR', 'ACTIVE')
ON DUPLICATE KEY UPDATE
    sensor_name = VALUES(sensor_name),
    sensor_type = VALUES(sensor_type),
    status = VALUES(status);

-- 4. Register Nagpur Edge IoT Device (Simulated / Physical Unit)
INSERT INTO iot_devices (
    device_id, device_name, device_model, location_id, status
) VALUES (
    'ARDUINO_UNO_NAG_01', 'Nagpur Zero Mile Edge Unit (Simulated)', 'Arduino Uno R3', 'LOC_NAGPUR', 'OFFLINE'
)
ON DUPLICATE KEY UPDATE
    device_name = VALUES(device_name),
    location_id = VALUES(location_id);
