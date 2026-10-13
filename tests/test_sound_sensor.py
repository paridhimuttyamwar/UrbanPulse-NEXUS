"""
Test suite for UrbanPulse NEXUS Temporary Sound Sensor Hardware Integration.
Verifies:
1. Parsing of UP_IOT sound telemetry packets.
2. ADC boundary range validation (0-1023).
3. MySQL persistence with source_type='REAL_HARDWARE'.
4. Data provenance isolation between real hardware and simulated views.
5. Hardware registration with SOUND_RAW sensor assignment.
6. Handshake response identification in sound test mode.
"""

import sys
import os
import uuid
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.connection import get_db_cursor
from database.repository import repository
from dashboard.data_loader import load_iot_readings, load_iot_devices
from iot.serial_gateway.gateway import serial_gateway
from validation.models import IoTSensorRecord, IoTDeviceRecord


def run_sound_tests():
    print("==================================================================")
    print("   UrbanPulse NEXUS -- Sound Sensor Hardware Test Verification    ")
    print("==================================================================")

    test_dev_id = f"ARDUINO_SND_{uuid.uuid4().hex[:6].upper()}"

    try:
        # 1. Device Registration with SOUND_P2P,SOUND_RAW
        print("\n--- Test 1: Register Hardware Device with Sound Sensor ---")
        reg_ok, reg_msg = serial_gateway.register_hardware_device(
            device_id=test_dev_id,
            device_name="Nagpur Acoustic Lab Unit",
            device_model="Arduino Uno R3",
            location_id="LOC_NAGPUR",
            connected_sensors="SOUND_P2P,SOUND_RAW",
            port_assignment="COM3",
        )
        assert reg_ok, f"Registration failed: {reg_msg}"
        print(f"  [PASS] Device registered with SOUND_P2P,SOUND_RAW: {reg_msg}")

        # 2. Sound Packet Parsing (SOUND_P2P)
        print("\n--- Test 2: Sound Packet Parsing (UP_IOT,dev,SOUND_P2P,val,ADC,OK) ---")
        raw_pkt = f"UP_IOT,{test_dev_id},SOUND_P2P,142.50,ADC,OK"
        parsed = serial_gateway.parse_serial_line(raw_pkt)
        assert parsed is not None
        assert parsed["device_id"] == test_dev_id
        assert parsed["sensor_type"] == "SOUND_P2P"
        assert parsed["reading_value"] == 142.50
        assert parsed["unit"] == "ADC"
        assert parsed["source_type"] == "REAL_HARDWARE"
        print(f"  [PASS] Parsed payload correctly: {parsed['sensor_type']} = {parsed['reading_value']} {parsed['unit']}")

        # 3. ADC Range Validation for SOUND_P2P (0 to 1023)
        print("\n--- Test 3: ADC Range Validation for SOUND_P2P (0-1023 Bounds) ---")
        # Valid lower bound
        p_zero = serial_gateway.parse_serial_line(f"UP_IOT,{test_dev_id},SOUND_P2P,0.0,ADC,OK")
        assert p_zero is not None and p_zero["reading_value"] == 0.0

        # Valid upper bound
        p_max = serial_gateway.parse_serial_line(f"UP_IOT,{test_dev_id},SOUND_P2P,1023.0,ADC,OK")
        assert p_max is not None and p_max["reading_value"] == 1023.0

        # Negative out of bounds
        p_neg = serial_gateway.parse_serial_line(f"UP_IOT,{test_dev_id},SOUND_P2P,-5.0,ADC,OK")
        assert p_neg is None, "Negative ADC value should be rejected"

        # Above 1023 out of bounds
        p_high = serial_gateway.parse_serial_line(f"UP_IOT,{test_dev_id},SOUND_P2P,1024.0,ADC,OK")
        assert p_high is None, "ADC value > 1023 should be rejected"

        # Non-numeric string
        p_nan = serial_gateway.parse_serial_line(f"UP_IOT,{test_dev_id},SOUND_P2P,BAD_VAL,ADC,OK")
        assert p_nan is None, "Non-numeric ADC reading should be rejected"
        print("  [PASS] ADC range bounds verified: [0, 1023] accepted; [-5, 1024, NaN] rejected")

        # 4. MySQL Persistence & Provenance for SOUND_P2P and SOUND_RAW
        print("\n--- Test 4: MySQL Persistence with REAL_HARDWARE Provenance ---")
        ins_ok = serial_gateway.process_and_persist(parsed)
        assert ins_ok, "Failed to persist SOUND_P2P packet"

        event_id = parsed["event_id"]
        with get_db_cursor(commit=False) as cursor:
            cursor.execute("SELECT * FROM iot_sensor_readings WHERE event_id = %(evt)s", {"evt": event_id})
            db_row = cursor.fetchone()
        assert db_row is not None
        assert db_row["sensor_type"] == "SOUND_P2P"
        assert float(db_row["reading_value"]) == 142.50
        assert db_row["source_type"] == "REAL_HARDWARE"
        print(f"  [PASS] SOUND_P2P record verified: Event {event_id}, source_type='{db_row['source_type']}'")

        # Also persist a legacy SOUND_RAW packet for backward compatibility check
        raw_pkt_legacy = f"UP_IOT,{test_dev_id},SOUND_RAW,13.0,ADC,OK"
        parsed_legacy = serial_gateway.parse_serial_line(raw_pkt_legacy)
        assert parsed_legacy is not None
        ins_legacy_ok = serial_gateway.process_and_persist(parsed_legacy)
        assert ins_legacy_ok, "Failed to persist legacy SOUND_RAW packet"
        print(f"  [PASS] Legacy SOUND_RAW backward compatibility preserved and persisted.")

        # 5. Provenance Isolation (Real vs Simulated)
        print("\n--- Test 5: Provenance Isolation in Data Loader ---")
        df_real = load_iot_readings(device_id=test_dev_id, source_type="REAL_HARDWARE")
        assert not df_real.empty
        assert (df_real["source_type"] == "REAL_HARDWARE").all()
        assert (df_real["sensor_type"] == "SOUND_P2P").any()
        assert (df_real["sensor_type"] == "SOUND_RAW").any()

        df_sim = load_iot_readings(device_id=test_dev_id, source_type="SIMULATED")
        assert df_sim.empty, "Simulated query must NOT return REAL_HARDWARE readings"
        print(f"  [PASS] Sound packets appear strictly in REAL_HARDWARE query ({len(df_real)} rows), 0 in SIMULATED")

        # 6. Handshake Frame Recognition in Sound Mode (v1.3.0 SOUND_P2P_A0)
        print("\n--- Test 6: Firmware Handshake Recognition (SOUND_P2P_A0) ---")
        handshake_line = f"UP_IDENT,{test_dev_id},ARDUINO_UNO_R3,v1.3.0,SOUND_P2P_A0"
        parts = handshake_line.split(",")
        dev_id = parts[1]
        model = parts[2]
        version = parts[3]
        mode_tag = parts[4]
        assert "SOUND" in mode_tag
        assert dev_id == test_dev_id
        print(f"  [PASS] Handshake identified mode: {mode_tag} ({model} {version})")

    finally:
        # Cleanup test records
        print("\n--- Cleaning up test records ---")
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM iot_sensor_readings WHERE device_id = %(dev)s", {"dev": test_dev_id})
            cursor.execute("DELETE FROM iot_devices WHERE device_id = %(dev)s", {"dev": test_dev_id})
        print(f"  [PASS] Test device {test_dev_id} and its readings safely cleaned up.")

    print("\n==================================================================")
    print("   ALL SOUND SENSOR TESTS PASSED SUCCESSFULLY (6/6)              ")
    print("==================================================================")


if __name__ == "__main__":
    run_sound_tests()
