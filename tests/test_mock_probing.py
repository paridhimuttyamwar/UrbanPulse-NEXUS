"""
UrbanPulse NEXUS — Isolated Unit Test for Serial Port Probing & Error Handling (Test 9)
Runs purely in-memory with zero hardware, zero database access, and zero Kafka overhead.
Executes in under 100ms.
"""

import os
import sys
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 1. Mock Kafka Producer before importing gateway to prevent network timeouts
with patch("streaming.producers.traffic_producer.TrafficKafkaProducer"):
    from iot.serial_gateway.gateway import serial_gateway


class MockSerialBase:
    """Mock serial stream base class."""
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


class MockSerialTimeout(MockSerialBase):
    def __init__(self, *args, **kwargs):
        super().__init__([])


def run_isolated_test_9():
    print("=" * 70)
    print("   UrbanPulse NEXUS: Isolated Test 9 (Mock Serial Probing)       ")
    print("=" * 70)

    total_checks = 0
    passed_checks = 0

    # -------------------------------------------------------------
    # Subtest 9A: Mock Serial Raising PermissionError (Access Denied / Busy Port)
    # -------------------------------------------------------------
    total_checks += 1
    print("\n--- Subtest 9A: Port Occupied / PermissionError Handling ---")
    with patch("serial.Serial", side_effect=PermissionError("Access is denied")):
        ok, msg, meta = serial_gateway.verify_hardware_handshake("COM7", baud_rate=9600, timeout=0.1)
        if ok is False and meta and meta.get("error_type") == "PORT_BUSY":
            print(f"  [PASS] PermissionError handled gracefully as PORT_BUSY: {msg}")
            passed_checks += 1
        else:
            print(f"  [FAIL] Expected ok=False and error_type=PORT_BUSY. Got ok={ok}, meta={meta}")

    # -------------------------------------------------------------
    # Subtest 9B: Mock Serial Timeout (No Handshake Received)
    # -------------------------------------------------------------
    total_checks += 1
    print("\n--- Subtest 9B: Probing Timeout Handling ---")
    with patch("serial.Serial", side_effect=MockSerialTimeout), patch("time.sleep", return_value=None):
        ok, msg, meta = serial_gateway.verify_hardware_handshake("COM7", baud_rate=9600, timeout=0.1)
        if ok is False and meta is None and "no valid urbanpulse handshake" in msg.lower():
            print(f"  [PASS] Timeout handled gracefully without exception: {msg}")
            passed_checks += 1
        else:
            print(f"  [FAIL] Expected ok=False and meta=None. Got ok={ok}, msg={msg}")

    # -------------------------------------------------------------
    # Subtest 9C: Mock Serial Disconnection / FileNotFoundError
    # -------------------------------------------------------------
    total_checks += 1
    print("\n--- Subtest 9C: Physical Device Disconnected Handling ---")
    with patch("serial.Serial", side_effect=FileNotFoundError("could not open port COM7")):
        ok, msg, meta = serial_gateway.verify_hardware_handshake("COM7", baud_rate=9600, timeout=0.1)
        if ok is False and meta and meta.get("error_type") == "DISCONNECTED":
            print(f"  [PASS] Disconnection handled gracefully as DISCONNECTED: {msg}")
            passed_checks += 1
        else:
            print(f"  [FAIL] Expected ok=False and error_type=DISCONNECTED. Got ok={ok}, meta={meta}")

    print("\n" + "=" * 70)
    print(f"   TEST 9 RESULT: {passed_checks}/{total_checks} CHECKS PASSED")
    print("=" * 70)

    if passed_checks == total_checks:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    run_isolated_test_9()
