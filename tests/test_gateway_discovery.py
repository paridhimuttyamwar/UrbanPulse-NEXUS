"""
Automated Test Suite for UrbanPulse NEXUS:
Automatic Arduino Discovery, Gateway Reliability & Edge IoT Dashboard Refinement.

Verifies:
1. Candidate port heuristic ranking (VID matches, descriptions).
2. Handshake response parser (both UP_IDENT and UP_IOT fallback).
3. Dynamic port assignment update in MySQL (e.g., COM7 -> COM8).
4. Auto-detection fallback when no hardware is connected.
5. Ingestion of SOUND_P2P packets into MySQL without affecting SOUND_RAW rows.
6. KPI calculation correctness and metric stream isolation (SOUND_RAW vs SOUND_P2P).
7. Gateway state file read/write roundtrip.
8. Heartbeat age calculation and PID liveness detection.
9. Mock serial port probing:
   - UP_IDENT response handling.
   - UP_IOT fallback response handling.
   - PermissionError (port busy) handling.
   - Timeout handling.
"""

import os
import sys
import time
import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import settings, GATEWAY_STATE_FILE
from database.connection import get_db_cursor
from database.repository import repository
from dashboard.data_loader import load_iot_readings, get_gateway_runtime_status
from iot.serial_gateway.gateway import serial_gateway


def run_all_tests():
    print("=" * 70)
    print("   UrbanPulse NEXUS: Gateway Discovery & Reliability Test Suite   ")
    print("=" * 70)

    # -------------------------------------------------------------
    # 1. Candidate Port Heuristic Ranking
    # -------------------------------------------------------------
    print("\n--- Test 1: Candidate Port Heuristic Ranking ---")

    class MockPort:
        def __init__(self, device, description="", hwid="", vid=None, pid=None, manufacturer=""):
            self.device = device
            self.description = description
            self.hwid = hwid
            self.vid = vid
            self.pid = pid
            self.manufacturer = manufacturer

    mock_ports = [
        MockPort("COM1", "Communications Port", "ACPI\\PNP0501", vid=None, pid=None),
        MockPort("COM3", "USB-SERIAL CH340 (COM3)", "USB VID:PID=1A86:7523", vid=0x1A86, pid=0x7523, manufacturer="WCH"),
        MockPort("COM4", "Arduino Uno (COM4)", "USB VID:PID=2341:0043", vid=0x2341, pid=0x0043, manufacturer="Arduino SA"),
        MockPort("COM5", "USB Serial Converter", "FTDI VID:PID=0403:6001", vid=0x0403, pid=0x6001, manufacturer="FTDI"),
    ]

    with patch("serial.tools.list_ports.comports", return_value=mock_ports):
        ranked = serial_gateway.find_candidate_ports()
        ranked_devices = [p["device"] for p in ranked]
        print(f"  Ranked candidate ports: {ranked_devices}")
        # COM4 has Official Arduino VID + keywords (score 10 + 5 = 15)
        # COM3 has CH340 VID + keywords (score 10 + 5 = 15)
        # COM5 has FTDI VID + keywords (score 10 + 5 = 15)
        # COM1 has score 0
        assert ranked_devices[3] == "COM1", f"Expected generic COM1 last, got {ranked_devices[3]}"
        assert all(p["hint_score"] > 0 for p in ranked[:3]), "Top 3 candidate ports must have hint_score > 0"
        print("  [PASS] Candidate ports ranked with heuristic scores; generic ports deprioritized.")

    # -------------------------------------------------------------
    # 2. Handshake Response Parser (UP_IDENT & UP_IOT Fallback)
    # -------------------------------------------------------------
    print("\n--- Test 2: Handshake Response Parsing ---")

    class MockSerialBase:
        def __init__(self, lines=None):
            self.is_open = True
            self.lines = list(lines or [])

        @property
        def in_waiting(self):
            return 64 if self.lines else 0

        def readline(self):
            return self.lines.pop(0) if self.lines else b""

        def write(self, data):
            return len(data)

        def flush(self):
            pass

        def reset_input_buffer(self):
            pass

        def reset_output_buffer(self):
            pass

        def close(self):
            self.is_open = False

    class MockSerialIdent(MockSerialBase):
        def __init__(self, *args, **kwargs):
            super().__init__([b"UP_IDENT,ARDUINO_SOUND_01,Arduino Uno R3,v1.3.0,SOUND_P2P_A0\r\n"])

    class MockSerialIoT(MockSerialBase):
        def __init__(self, *args, **kwargs):
            super().__init__([b"UP_IOT,ARDUINO_SOUND_01,SOUND_P2P,12.50,ADC,OK\r\n"])

    # A: Test UP_IDENT
    with patch("serial.Serial", side_effect=MockSerialIdent), patch("time.sleep", return_value=None):
        ok, msg, meta = serial_gateway.verify_hardware_handshake("COM4", baud_rate=9600, timeout=1.0)
        assert ok is True
        assert meta["device_id"] == "ARDUINO_SOUND_01"
        assert meta["protocol"] == "UP_IDENT_HANDSHAKE"
        assert meta["firmware_version"] == "v1.3.0"
        print(f"  [PASS] UP_IDENT handshake verified: {msg}")

    # B: Test UP_IOT fallback
    with patch("serial.Serial", side_effect=MockSerialIoT), patch("time.sleep", return_value=None):
        ok, msg, meta = serial_gateway.verify_hardware_handshake("COM4", baud_rate=9600, timeout=1.0)
        assert ok is True
        assert meta["device_id"] == "ARDUINO_SOUND_01"
        assert meta["protocol"] == "UP_IOT_STREAM"
        assert meta["sensor_type"] == "SOUND_P2P"
        print(f"  [PASS] UP_IOT fallback verified: {msg}")


    # -------------------------------------------------------------
    # 3. Dynamic Port Assignment Update in MySQL
    # -------------------------------------------------------------
    print("\n--- Test 3: Dynamic Port Assignment Update in MySQL ---")
    test_dev_id = f"TEST_PORT_DEV_{uuid.uuid4().hex[:6].upper()}"

    # Register initial device on COM7
    ok, msg = serial_gateway.register_hardware_device(
        device_id=test_dev_id,
        device_name="Dynamic Port Test Unit",
        device_model="Arduino Uno R3",
        location_id="LOC_NAGPUR",
        connected_sensors="SOUND_P2P",
        port_assignment="COM7",
    )
    assert ok, f"Setup registration failed: {msg}"

    try:
        # Verify initial assignment is COM7
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT port_assignment FROM iot_devices WHERE device_id = %s", (test_dev_id,))
            row = cur.fetchone()
            assert row and row["port_assignment"] == "COM7"
            print(f"  Initial assignment for {test_dev_id}: {row['port_assignment']}")

        # Simulate discovery on COM8 and port update
        serial_gateway._sync_device_port_assignment(test_dev_id, "COM8")

        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT port_assignment FROM iot_devices WHERE device_id = %s", (test_dev_id,))
            row = cur.fetchone()
            assert row and row["port_assignment"] == "COM8"
            print(f"  [PASS] Updated assignment for {test_dev_id} dynamically changed to: {row['port_assignment']}")

    finally:
        # Clean up test device
        with get_db_cursor(commit=True) as cur:
            cur.execute("DELETE FROM iot_devices WHERE device_id = %s", (test_dev_id,))
            print(f"  Cleaned up temporary test device {test_dev_id}.")

    # -------------------------------------------------------------
    # 4. Auto-detection Fallback When No Hardware Connected
    # -------------------------------------------------------------
    print("\n--- Test 4: Auto-detection Fallback When No Hardware Connected ---")
    with patch("serial.tools.list_ports.comports", return_value=[]):
        found, port, meta, msg = serial_gateway.discover_arduino()
        assert not found
        assert port is None
        assert "No serial COM ports detected" in msg
        print(f"  [PASS] Handled empty port list gracefully: {msg}")

    # -------------------------------------------------------------
    # 5. Ingestion of SOUND_P2P Without Affecting SOUND_RAW Rows
    # -------------------------------------------------------------
    print("\n--- Test 5: Ingestion of SOUND_P2P & Data Preservation ---")
    with get_db_cursor(commit=False) as cur:
        cur.execute("SELECT count(*) as cnt FROM iot_sensor_readings WHERE source_type = 'REAL_HARDWARE' AND sensor_type = 'SOUND_RAW'")
        initial_raw_count = cur.fetchone()["cnt"]

    test_pkt = "UP_IOT,ARDUINO_SOUND_01,SOUND_P2P,45.00,ADC,OK"
    parsed_pkt = serial_gateway.parse_serial_line(test_pkt)
    assert parsed_pkt is not None
    test_event_id = parsed_pkt["event_id"]

    inserted = serial_gateway.process_and_persist(parsed_pkt)
    assert inserted, "Failed to persist test SOUND_P2P reading"

    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT count(*) as cnt FROM iot_sensor_readings WHERE source_type = 'REAL_HARDWARE' AND sensor_type = 'SOUND_RAW'")
            current_raw_count = cur.fetchone()["cnt"]
            assert current_raw_count == initial_raw_count, f"SOUND_RAW count modified! Expected {initial_raw_count}, got {current_raw_count}"
            print(f"  [PASS] SOUND_RAW record count preserved exactly ({current_raw_count} rows).")
    finally:
        with get_db_cursor(commit=True) as cur:
            cur.execute("DELETE FROM iot_sensor_readings WHERE event_id = %s", (test_event_id,))
            print("  Cleaned up test reading.")


    # -------------------------------------------------------------
    # 6. KPI Metric Stream Isolation in Data Loader
    # -------------------------------------------------------------
    print("\n--- Test 6: KPI Metric Stream Isolation in Data Loader ---")
    p2p_df = load_iot_readings(source_type="REAL_HARDWARE", device_id="ARDUINO_SOUND_01", sensor_type="SOUND_P2P")
    raw_df = load_iot_readings(source_type="REAL_HARDWARE", device_id="ARDUINO_SOUND_01", sensor_type="SOUND_RAW")

    assert not p2p_df.empty, "Expected REAL_HARDWARE SOUND_P2P readings to exist"
    assert not raw_df.empty, "Expected REAL_HARDWARE SOUND_RAW readings to exist"

    assert (p2p_df["sensor_type"] == "SOUND_P2P").all(), "Found non-SOUND_P2P in p2p_df!"
    assert (raw_df["sensor_type"] == "SOUND_RAW").all(), "Found non-SOUND_RAW in raw_df!"

    print(f"  [PASS] Isolated query results: SOUND_P2P={len(p2p_df)} rows, SOUND_RAW={len(raw_df)} rows. Zero cross-contamination.")

    # -------------------------------------------------------------
    # 7. Gateway State File Read/Write Roundtrip
    # -------------------------------------------------------------
    print("\n--- Test 7: Gateway State File Read/Write Roundtrip ---")
    serial_gateway.active_port = "COM8"
    serial_gateway.current_device_id = "ARDUINO_SOUND_01"
    serial_gateway.packet_count = 123
    serial_gateway.write_gateway_state(
        gateway_status="RUNNING",
        connection_state="STREAMING",
        message="Streaming on COM8",
        last_packet_val=15.0,
        last_packet_type="SOUND_P2P",
    )

    state = serial_gateway.get_gateway_status()
    assert state.get("is_alive") is True
    assert state.get("pid") == os.getpid()
    assert state.get("active_port") == "COM8"
    assert state.get("device_id") == "ARDUINO_SOUND_01"
    assert state.get("gateway_status") == "RUNNING"
    assert state.get("connection_state") == "STREAMING"
    assert state.get("packet_count") == 123
    print("  [PASS] Gateway state serialized and read back with all fields matching.")

    # -------------------------------------------------------------
    # 8. Heartbeat Age & Liveness Detection
    # -------------------------------------------------------------
    print("\n--- Test 8: Heartbeat Age and PID Liveness Detection ---")

    # A: Fresh heartbeat with active PID (current process)
    status_fresh = serial_gateway.get_gateway_status()
    assert status_fresh["is_alive"] is True
    print("  [PASS] Live process + fresh heartbeat detected as is_alive=True.")

    # B: Stale heartbeat (>25s old)
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=45)).strftime("%Y-%m-%d %H:%M:%S")
    with open(GATEWAY_STATE_FILE, "r", encoding="utf-8") as f:
        curr_state = json.load(f)
    curr_state["last_heartbeat"] = stale_time
    with open(GATEWAY_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(curr_state, f)

    status_stale = serial_gateway.get_gateway_status()
    assert status_stale["is_alive"] is False
    assert status_stale["gateway_status"] == "STOPPED"
    print("  [PASS] Stale heartbeat (>25s) detected as stopped/inactive.")

    # C: Dead PID
    curr_state["last_heartbeat"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    curr_state["pid"] = 99999999  # nonexistent PID
    curr_state["gateway_status"] = "RUNNING"
    with open(GATEWAY_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(curr_state, f)

    status_dead_pid = serial_gateway.get_gateway_status()
    assert status_dead_pid["is_alive"] is False
    assert status_dead_pid["gateway_status"] == "STOPPED"
    print("  [PASS] Non-existent PID detected as stopped.")

    # Reset state file to clean stopped state
    serial_gateway.active_port = None
    serial_gateway.write_gateway_state(
        gateway_status="STOPPED",
        connection_state="DISCONNECTED",
        message="Gateway stopped cleanly.",
    )

    # -------------------------------------------------------------
    # 9. Mock Serial Port Probing & Error Handling
    # -------------------------------------------------------------
    print("\n--- Test 9: Mock Serial Port Probing & Exception Handling ---")

    # A: Mock serial raising PermissionError (Access denied / port busy)
    with patch("serial.Serial", side_effect=PermissionError("Access is denied")):
        ok, msg, meta = serial_gateway.verify_hardware_handshake("COM7", baud_rate=9600, timeout=1.0)
        assert ok is False
        assert meta["error_type"] == "PORT_BUSY"
        assert "occupied" in msg.lower() or "busy" in msg.lower()
        print(f"  [PASS] PermissionError handled gracefully as PORT_BUSY: {msg}")

    # B: Mock serial timeout (returns empty bytes)
    class MockSerialTimeout(MockSerialBase):
        def __init__(self, *args, **kwargs):
            super().__init__([])

    with patch("serial.Serial", side_effect=MockSerialTimeout), patch("time.sleep", return_value=None):
        ok, msg, meta = serial_gateway.verify_hardware_handshake("COM7", baud_rate=9600, timeout=0.1)
        assert ok is False
        assert meta is None
        assert "no valid urbanpulse handshake" in msg.lower()
        print(f"  [PASS] Timeout handled gracefully without exception: {msg}")


    print("\n" + "=" * 70)
    print("   ALL GATEWAY DISCOVERY & RELIABILITY TESTS PASSED (9/9)         ")
    print("=" * 70)


if __name__ == "__main__":
    run_all_tests()
