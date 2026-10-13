-- UrbanPulse Initial Seed Data

USE urbanpulse;

-- 1. Insert Locations
INSERT INTO locations (location_id, city_name, state_name, country, latitude, longitude, timezone)
VALUES
('LOC_PUNE', 'Pune', 'Maharashtra', 'India', 18.520430, 73.856744, 'Asia/Kolkata'),
('LOC_MUMBAI', 'Mumbai', 'Maharashtra', 'India', 19.076090, 72.877426, 'Asia/Kolkata'),
('LOC_BLR', 'Bengaluru', 'Karnataka', 'India', 12.971599, 77.594566, 'Asia/Kolkata'),
('LOC_DELHI', 'New Delhi', 'Delhi', 'India', 28.613939, 77.209023, 'Asia/Kolkata')
ON DUPLICATE KEY UPDATE 
    city_name = VALUES(city_name),
    latitude = VALUES(latitude),
    longitude = VALUES(longitude);

-- 2. Insert 15 Road Segments (Focusing on Pune & Mumbai urban corridors)
INSERT INTO road_segments (segment_id, location_id, road_name, segment_type, speed_limit_kmh, length_km, capacity_vph)
VALUES
('SEG_PUN_01', 'LOC_PUNE', 'FC Road (Fergusson College Rd)', 'DOWNTOWN', 40, 2.50, 2200),
('SEG_PUN_02', 'LOC_PUNE', 'JM Road (Jangali Maharaj Rd)', 'DOWNTOWN', 40, 2.80, 2500),
('SEG_PUN_03', 'LOC_PUNE', 'Senapati Bapat Road', 'ARTERIAL', 50, 3.20, 2800),
('SEG_PUN_04', 'LOC_PUNE', 'Pune-Bangalore Highway (NH48 Baner)', 'HIGHWAY', 80, 6.50, 4500),
('SEG_PUN_05', 'LOC_PUNE', 'Hinjawadi Phase 1 IT Spine', 'ARTERIAL', 45, 4.00, 3200),
('SEG_PUN_06', 'LOC_PUNE', 'Hinjawadi Phase 2 Main Road', 'ARTERIAL', 45, 3.50, 2600),
('SEG_PUN_07', 'LOC_PUNE', 'Karve Road (Deccan to Kothrud)', 'ARTERIAL', 45, 4.20, 3000),
('SEG_PUN_08', 'LOC_PUNE', 'Koregaon Park North Main Rd', 'SUBURBAN', 40, 2.10, 1800),
('SEG_PUN_09', 'LOC_PUNE', 'Viman Nagar Central Avenue', 'SUBURBAN', 40, 2.40, 1900),
('SEG_PUN_10', 'LOC_PUNE', 'Nagar Road (Yerawada Corridor)', 'ARTERIAL', 60, 5.00, 3800),
('SEG_MUM_01', 'LOC_MUMBAI', 'Western Express Highway (Andheri)', 'HIGHWAY', 70, 7.00, 5000),
('SEG_MUM_02', 'LOC_MUMBAI', 'Eastern Freeway (Chembur to Fort)', 'HIGHWAY', 80, 8.50, 4800),
('SEG_MUM_03', 'LOC_MUMBAI', 'Bandra-Worli Sea Link', 'HIGHWAY', 80, 5.60, 4200),
('SEG_MUM_04', 'LOC_MUMBAI', 'Linking Road (Bandra West)', 'DOWNTOWN', 35, 2.30, 2100),
('SEG_MUM_05', 'LOC_MUMBAI', 'SVT Road / Juhu Tara Road', 'ARTERIAL', 40, 3.10, 2000)
ON DUPLICATE KEY UPDATE 
    road_name = VALUES(road_name),
    speed_limit_kmh = VALUES(speed_limit_kmh),
    capacity_vph = VALUES(capacity_vph);

-- 3. Insert Traffic Sensors for Road Segments
INSERT INTO traffic_sensors (sensor_id, segment_id, sensor_name, sensor_type, status)
VALUES
('SNS_TRF_PUN_01', 'SEG_PUN_01', 'FCR Inductive Loop A', 'LOOP_DETECTOR', 'ACTIVE'),
('SNS_TRF_PUN_02', 'SEG_PUN_02', 'JMR Camera Radar B', 'RADAR', 'ACTIVE'),
('SNS_TRF_PUN_03', 'SEG_PUN_03', 'SBR Sensor Pod 1', 'LOOP_DETECTOR', 'ACTIVE'),
('SNS_TRF_PUN_04', 'SEG_PUN_04', 'Baner Highway Flow Meter', 'RADAR', 'ACTIVE'),
('SNS_TRF_PUN_05', 'SEG_PUN_05', 'Hinjawadi IT Gate Loop', 'LOOP_DETECTOR', 'ACTIVE'),
('SNS_TRF_PUN_06', 'SEG_PUN_06', 'Phase 2 Wipro Circle Cam', 'RADAR', 'ACTIVE'),
('SNS_TRF_PUN_07', 'SEG_PUN_07', 'Karve Rd Paud Phata Unit', 'LOOP_DETECTOR', 'ACTIVE'),
('SNS_TRF_PUN_08', 'SEG_PUN_08', 'KP Lane 1 Acoustic Sensor', 'ACOUSTIC', 'ACTIVE'),
('SNS_TRF_PUN_09', 'SEG_PUN_09', 'Viman Nagar Crossing 2', 'LOOP_DETECTOR', 'ACTIVE'),
('SNS_TRF_PUN_10', 'SEG_PUN_10', 'Yerawada Bridge Radar', 'RADAR', 'ACTIVE'),
('SNS_TRF_MUM_01', 'SEG_MUM_01', 'WEH Andheri Flyover Sensor', 'RADAR', 'ACTIVE'),
('SNS_TRF_MUM_02', 'SEG_MUM_02', 'Eastern Freeway Toll Pod', 'LOOP_DETECTOR', 'ACTIVE'),
('SNS_TRF_MUM_03', 'SEG_MUM_03', 'Sea Link North Gantry', 'RADAR', 'ACTIVE'),
('SNS_TRF_MUM_04', 'SEG_MUM_04', 'Linking Rd Market Radar', 'LOOP_DETECTOR', 'ACTIVE'),
('SNS_TRF_MUM_05', 'SEG_MUM_05', 'Juhu Beach Approach Loop', 'LOOP_DETECTOR', 'ACTIVE')
ON DUPLICATE KEY UPDATE 
    sensor_name = VALUES(sensor_name),
    status = VALUES(status);

-- 4. Insert Default IoT Device (Arduino Uno R3)
INSERT INTO iot_devices (device_id, device_name, device_model, location_id, status)
VALUES
('ARDUINO_UNO_01', 'UrbanPulse Edge Unit 1', 'Arduino Uno R3', 'LOC_PUNE', 'OFFLINE')
ON DUPLICATE KEY UPDATE 
    device_name = VALUES(device_name);
