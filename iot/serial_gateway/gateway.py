"""
UrbanPulse PySerial Hardware Gateway.
Bridges physical Arduino Uno R3 USB serial communication with Kafka and MySQL.
Supports automatic COM port discovery, handshake identification, dynamic port tracking,
and resilient auto-reconnect backoff while preserving strict REAL_HARDWARE data provenance.
"""

import os
import sys
import json
import logging
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List

try:
    import serial
    from serial.tools import list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

from config.settings import settings
from database.connection import get_db_cursor
from database.repository import repository
from storage.raw_archiver import archiver
from validation.validator import ValidationEngine
from streaming.producers.traffic_producer import TrafficKafkaProducer

logger = logging.getLogger(__name__)

# Known USB Vendor IDs and keywords for Arduino / CH340 / USB-Serial devices
KNOWN_ARDUINO_VIDS = {
    0x2341: "Arduino SA",
    0x2A03: "Arduino srl",
    0x1A86: "WCH (CH340/CH341)",
    0x0403: "FTDI",
    0x10C4: "Silicon Labs (CP210x)",
}

KNOWN_DEVICE_KEYWORDS = [
    "arduino",
    "ch340",
    "ch341",
    "usb-serial",
    "usb serial",
    "ftdi",
    "cp210",
    "serial",
]


class ArduinoSerialGateway:
    def __init__(
        self,
        port: Optional[str] = None,
        baud_rate: Optional[int] = None,
    ):
        raw_port = port or settings.ARDUINO_PORT
        self.port = raw_port
        self.port_mode = "AUTO" if str(raw_port).strip().upper() == "AUTO" else "MANUAL"
        self.active_port: Optional[str] = None
        self.current_device_id = "ARDUINO_SOUND_01"
        self.firmware_version = "v1.3.0"
        self.baud_rate = baud_rate or settings.ARDUINO_BAUD_RATE
        self.serial_conn: Optional[Any] = None
        self.is_connected = False
        self.packet_count = 0
        self.last_packet_time: Optional[str] = None
        self.producer = TrafficKafkaProducer()

    def find_available_ports(self) -> List[str]:
        """Scans for active serial ports on Windows."""
        if not HAS_SERIAL:
            return []
        ports = list_ports.comports()
        return [p.device for p in ports]

    def probe_ports_detailed(self) -> List[Dict[str, Any]]:
        """Returns detailed port information including hardware descriptions."""
        if not HAS_SERIAL:
            return []
        ports = list_ports.comports()
        results = []
        for p in ports:
            results.append({
                "device": p.device,
                "description": p.description or "Generic Serial Port",
                "hwid": p.hwid or "Unknown HWID",
                "vid": getattr(p, "vid", None),
                "pid": getattr(p, "pid", None),
                "manufacturer": getattr(p, "manufacturer", None) or "Unknown",
            })
        return results

    def find_candidate_ports(self) -> List[Dict[str, Any]]:
        """
        Enumerates available serial ports on the host and scores them based on USB metadata hints.
        Treats USB metadata only as a discovery hint, not as proof of device identity.
        """
        if not HAS_SERIAL:
            return []

        ports = list_ports.comports()
        candidates = []

        for p in ports:
            score = 0
            vid = getattr(p, "vid", None)
            pid = getattr(p, "pid", None)
            desc = (getattr(p, "description", "") or "").lower()
            mfr = (getattr(p, "manufacturer", "") or "").lower()
            hwid = (getattr(p, "hwid", "") or "").lower()

            # Priority 1: Known VID
            if vid in KNOWN_ARDUINO_VIDS:
                score += 10

            # Priority 2: Keywords in description, manufacturer, or HWID
            for kw in KNOWN_DEVICE_KEYWORDS:
                if kw in desc or kw in mfr or kw in hwid:
                    score += 5
                    break

            candidates.append({
                "device": p.device,
                "description": p.description or "Generic Serial Port",
                "manufacturer": getattr(p, "manufacturer", None) or "Unknown",
                "hwid": p.hwid or "Unknown HWID",
                "vid": vid,
                "pid": pid,
                "hint_score": score,
                "is_likely_arduino": score > 0,
            })

        # Sort candidate ports: highest hint score first
        candidates.sort(key=lambda x: x["hint_score"], reverse=True)
        return candidates

    def verify_hardware_handshake(
        self,
        port: str,
        baud_rate: int = 9600,
        timeout: float = 2.5,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Actively probes a serial port to verify an authentic UrbanPulse Arduino.
        Sends a 'PING' command and expects an 'UP_IDENT' handshake response,
        or accepts an incoming 'UP_IOT' data stream frame.
        Handles access-denied ports and resets gracefully.
        """
        if not HAS_SERIAL:
            return False, "PySerial library is not installed on this host.", None

        conn = None
        try:
            logger.info(f"Probing port {port} at {baud_rate} baud for Arduino handshake...")
            conn = serial.Serial(
                port=port,
                baudrate=baud_rate,
                timeout=1.0,
                write_timeout=1.0,
            )
            time.sleep(1.8)  # Wait for Arduino DTR auto-reset
            conn.reset_input_buffer()
            conn.reset_output_buffer()

            # Transmit handshake request
            conn.write(b"PING\n")
            conn.flush()

            start_t = time.time()
            dev_meta = {
                "port": port,
                "baud_rate": baud_rate,
                "verified_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            }

            while time.time() - start_t < timeout:
                if conn.in_waiting > 0:
                    raw_b = conn.readline()
                    line = raw_b.decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue

                    # Case 1: Direct Handshake Response: UP_IDENT,DEVICE_ID,MODEL,VERSION,MODE
                    if line.startswith("UP_IDENT"):
                        parts = line.split(",")
                        dev_id = parts[1] if len(parts) > 1 else "ARDUINO_SOUND_01"
                        model = parts[2] if len(parts) > 2 else "Arduino Uno R3"
                        version = parts[3] if len(parts) > 3 else "v1.3.0"
                        mode_tag = parts[4] if len(parts) > 4 else "STANDARD"
                        dev_meta.update({
                            "device_id": dev_id,
                            "device_model": model,
                            "firmware_version": version,
                            "mode": mode_tag,
                            "protocol": "UP_IDENT_HANDSHAKE",
                        })
                        mode_desc = "Sound Sensor Test Mode" if "SOUND" in mode_tag else f"Mode: {mode_tag}"
                        return True, f"Verified UrbanPulse Arduino on {port}: {model} ({version}, {mode_desc}, ID: {dev_id})", dev_meta

                    # Case 2: Active CSV Packet Stream: UP_IOT,DEVICE_ID,SENSOR_TYPE,...
                    elif line.startswith("UP_IOT"):
                        parts = line.split(",")
                        dev_id = parts[1] if len(parts) > 1 else "ARDUINO_SOUND_01"
                        s_type = parts[2] if len(parts) > 2 else "UNKNOWN"
                        dev_meta.update({
                            "device_id": dev_id,
                            "device_model": "Arduino Uno R3",
                            "protocol": "UP_IOT_STREAM",
                            "sensor_type": s_type,
                            "mode": "ACTIVE_STREAM",
                        })
                        s_desc = (
                            "Sound Sensor Stream (P2P Amplitude)"
                            if s_type == "SOUND_P2P"
                            else ("Sound Sensor Stream (Raw)" if s_type == "SOUND_RAW" else f"Sensor: {s_type}")
                        )
                        return True, f"Verified active UrbanPulse telemetry stream on {port} (Node: {dev_id}, {s_desc})", dev_meta

                    elif line.startswith("#"):
                        # Boot banner
                        dev_meta["boot_banner"] = line

                time.sleep(0.05)

            return (
                False,
                f"No valid UrbanPulse handshake response received on {port} within {timeout}s. "
                "Ensure urbanpulse_firmware.ino is uploaded and configured at 9600 baud.",
                None,
            )
        except (serial.SerialException, PermissionError, OSError) as se:
            err_str = str(se)
            if isinstance(se, PermissionError) or "PermissionError" in err_str or "Access is denied" in err_str or "Permission denied" in err_str:
                return (
                    False,
                    f"Permission denied accessing {port}: The port is occupied by another process "
                    "(e.g. active Gateway process or Arduino IDE Serial Monitor).",
                    {"port": port, "error_type": "PORT_BUSY"},
                )
            elif isinstance(se, FileNotFoundError) or "FileNotFoundError" in err_str or "could not open port" in err_str:
                return (
                    False,
                    f"Serial port {port} could not be opened: Physical device disconnected.",
                    {"port": port, "error_type": "DISCONNECTED"},
                )
            return False, f"Serial communication error on {port}: {err_str}", {"port": port, "error_type": "SERIAL_ERROR"}
        except Exception as e:
            return False, f"Unexpected error probing {port}: {e}", None
        finally:
            if conn and conn.is_open:
                try:
                    conn.close()
                except Exception:
                    pass

    def discover_arduino(
        self,
        target_device_id: Optional[str] = None,
        baud_rate: Optional[int] = None,
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]], str]:
        """
        Scans all candidate serial ports, tests each candidate with verify_hardware_handshake,
        matches against registered physical devices or target_device_id, and updates MySQL port assignment.
        Returns: (is_found, port, dev_meta, message)
        """
        if not HAS_SERIAL:
            return False, None, None, "PySerial is not installed."

        candidates = self.find_candidate_ports()
        if not candidates:
            return False, None, None, "No serial COM ports detected on host."

        baud = baud_rate or self.baud_rate
        probed_ports = []

        # Check if external or local gateway process is already running and owns a port
        gw_status = self.get_gateway_status()
        if gw_status.get("is_alive") and gw_status.get("active_port"):
            active_p = gw_status.get("active_port")
            dev_id = gw_status.get("device_id") or "ARDUINO_SOUND_01"
            dev_meta = {
                "device_id": dev_id,
                "port": active_p,
                "baud_rate": gw_status.get("baud_rate", baud),
                "device_model": "Arduino Uno R3",
                "firmware_version": gw_status.get("firmware_version", "v1.3.0"),
                "status": gw_status.get("connection_state", "STREAMING"),
                "protocol": "ACTIVE_GATEWAY_LINK",
            }
            return True, active_p, dev_meta, f"Arduino verified — connected through active gateway on {active_p}."

        if self.is_connected and self.serial_conn and self.serial_conn.is_open:
            dev_meta = {
                "device_id": self.current_device_id,
                "port": self.active_port,
                "baud_rate": baud,
                "status": "STREAMING",
            }
            return True, self.active_port, dev_meta, f"Arduino verified — connected through active gateway on {self.active_port}."

        any_busy = False
        any_hardware = bool(candidates)
        for cand in candidates:
            port = cand["device"]
            probed_ports.append(port)
            ok, msg, meta = self.verify_hardware_handshake(port=port, baud_rate=baud, timeout=2.0)
            if ok and meta:
                dev_id = meta.get("device_id")
                # If target_device_id is specified, enforce match
                if target_device_id and dev_id != target_device_id:
                    logger.debug(f"Discovered Arduino {dev_id} on {port}, but does not match target {target_device_id}")
                    continue

                # Match against registered physical devices in MySQL or adopt this device
                self._sync_device_port_assignment(dev_id, port)
                return True, port, meta, f"Arduino verified — connected on {port} ({cand['description']})."
            elif meta and meta.get("error_type") == "PORT_BUSY":
                any_busy = True

        if any_busy:
            return False, None, None, "COM port busy — close the application using it before probing."
        elif any_hardware:
            return False, None, None, "Device detected, but UrbanPulse firmware verification failed."
        else:
            return False, None, None, "No Arduino detected."

    def _sync_device_port_assignment(self, device_id: str, port: str):
        """
        Updates the port_assignment in MySQL if the device changed COM ports.
        Treats COM port as a temporary connection attribute, not permanent identity.
        """
        try:
            with get_db_cursor(commit=True) as cursor:
                cursor.execute(
                    """
                    UPDATE iot_devices 
                    SET port_assignment = %(port)s 
                    WHERE device_id = %(dev)s AND device_type = 'PHYSICAL'
                    """,
                    {"port": port, "dev": device_id},
                )
        except Exception as e:
            logger.debug(f"Failed to update port_assignment in MySQL: {e}")

    @staticmethod
    def register_hardware_device(
        device_id: str,
        device_name: str,
        device_model: str = "Arduino Uno R3",
        location_id: str = "LOC_NAGPUR",
        connected_sensors: str = "SOUND_P2P,SOUND_RAW",
        port_assignment: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Registers a physical Arduino hardware node in MySQL.
        Guarantees device_type='PHYSICAL' and prevents unintended duplicates.
        """
        from validation.models import IoTDeviceRecord
        try:
            # Check for duplicate device_id
            with get_db_cursor(commit=False) as cursor:
                cursor.execute(
                    "SELECT device_id, device_name, device_type FROM iot_devices WHERE device_id = %(dev)s",
                    {"dev": device_id},
                )
                existing = cursor.fetchone()

            if existing:
                if existing["device_type"] == "PHYSICAL":
                    # Update configuration rather than erroring out
                    with get_db_cursor(commit=True) as cursor:
                        cursor.execute(
                            """
                            UPDATE iot_devices 
                            SET device_name = %(name)s, device_model = %(model)s,
                                location_id = %(loc)s, connected_sensors = %(sensors)s,
                                port_assignment = %(port)s
                            WHERE device_id = %(dev)s
                            """,
                            {
                                "name": device_name,
                                "model": device_model,
                                "loc": location_id,
                                "sensors": connected_sensors,
                                "port": port_assignment,
                                "dev": device_id,
                            },
                        )
                    return True, f"Hardware device '{device_id}' configuration updated successfully."
                else:
                    return False, f"Device ID '{device_id}' is already registered as a {existing['device_type']} node. Please choose a distinct hardware ID."

            # Register new physical device
            rec = IoTDeviceRecord(
                device_id=device_id,
                device_name=device_name,
                device_model=device_model,
                device_type="PHYSICAL",
                location_id=location_id,
                connected_sensors=connected_sensors,
                port_assignment=port_assignment,
                status="OFFLINE",
                last_heartbeat=None,
            )
            repository.insert_iot_device(rec)
            return True, f"Physical device '{device_name}' ({device_id}) registered successfully in MySQL."
        except Exception as e:
            logger.error(f"Failed to register hardware device: {e}")
            return False, f"Database error during registration: {e}"

    def connect(self) -> bool:
        """
        Connects to the physical Arduino.
        If self.port is 'AUTO' (or None), automatically discovers the active port.
        If manual port is specified, directly connects to that port.
        """
        if not HAS_SERIAL:
            logger.warning("pyserial is not installed.")
            return False

        # Close existing connection if open
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
            except Exception:
                pass

        resolved_port = None
        target_dev_id = getattr(self, "current_device_id", None) or "ARDUINO_SOUND_01"

        if self.port_mode == "AUTO":
            ok, port, meta, msg = self.discover_arduino(target_device_id=None)
            if ok and port:
                resolved_port = port
                if meta and meta.get("device_id"):
                    self.current_device_id = meta.get("device_id")
                    if meta.get("firmware_version"):
                        self.firmware_version = meta.get("firmware_version")
                logger.info(f"[AUTO DISCOVERY] {msg}")
            else:
                self.is_connected = False
                self.active_port = None
                self._update_device_status("OFFLINE", target_dev_id)
                self.write_gateway_state(
                    gateway_status="RUNNING",
                    connection_state="DISCONNECTED",
                    message="No Arduino detected on host USB ports.",
                )
                return False
        else:
            resolved_port = self.port

        try:
            logger.info(f"Connecting to Arduino on {resolved_port} @ {self.baud_rate} baud...")
            self.serial_conn = serial.Serial(
                port=resolved_port,
                baudrate=self.baud_rate,
                timeout=2,
            )
            time.sleep(2)  # Wait for Arduino auto-reset on DTR
            self.serial_conn.reset_input_buffer()
            self.is_connected = True
            self.active_port = resolved_port
            logger.info(f"Successfully connected to Arduino on {resolved_port}.")
            self._update_device_status("ONLINE", self.current_device_id)
            self.write_gateway_state(
                gateway_status="RUNNING",
                connection_state="STREAMING",
                message=f"Connected on {resolved_port}",
            )
            return True
        except serial.SerialException as se:
            err_str = str(se)
            logger.warning(f"Could not connect to Arduino on {resolved_port}: {se}")
            self.is_connected = False
            self.active_port = None
            self._update_device_status("OFFLINE", target_dev_id)
            conn_state = "PORT_BUSY" if ("PermissionError" in err_str or "Access is denied" in err_str) else "DISCONNECTED"
            self.write_gateway_state(
                gateway_status="RUNNING",
                connection_state=conn_state,
                message=f"Failed to open {resolved_port}: {err_str}",
            )
            return False

    def _update_device_status(self, status: str, device_id: str = "ARDUINO_SOUND_01"):
        """Updates device connection status and heartbeat in MySQL."""
        try:
            with get_db_cursor(commit=True) as cursor:
                if status == "ONLINE":
                    cursor.execute(
                        """
                        UPDATE iot_devices 
                        SET status = %(status)s, last_heartbeat = NOW() 
                        WHERE device_id = %(dev)s
                        """,
                        {"status": status, "dev": device_id},
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE iot_devices 
                        SET status = %(status)s 
                        WHERE device_id = %(dev)s
                        """,
                        {"status": status, "dev": device_id},
                    )
        except Exception as e:
            logger.debug(f"Device status update skipped: {e}")

    def write_gateway_state(
        self,
        gateway_status: str = "RUNNING",
        connection_state: str = "IDLE",
        message: str = "",
        last_packet_val: Optional[float] = None,
        last_packet_type: Optional[str] = None,
    ):
        """
        Persists runtime gateway state to data/gateway_state.json.
        Provides the dashboard with non-invasive, live process telemetry.
        """
        try:
            state_file = settings.GATEWAY_STATE_FILE
            state_file.parent.mkdir(parents=True, exist_ok=True)

            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            state_data = {
                "pid": os.getpid(),
                "gateway_status": gateway_status,
                "connection_state": connection_state,
                "port_mode": self.port_mode,
                "configured_port": self.port,
                "active_port": self.active_port,
                "baud_rate": self.baud_rate,
                "device_id": self.current_device_id,
                "firmware_version": getattr(self, "firmware_version", "v1.3.0"),
                "last_heartbeat": now_str,
                "last_packet_time": self.last_packet_time,
                "last_packet_val": last_packet_val,
                "last_packet_type": last_packet_type,
                "packet_count": self.packet_count,
                "auto_reconnect": True,
                "message": message,
            }

            temp_file = state_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2)
            temp_file.replace(state_file)
        except Exception as e:
            logger.debug(f"Failed to write gateway state file: {e}")

    @staticmethod
    def get_gateway_status() -> Dict[str, Any]:
        """
        Reads data/gateway_state.json and verifies process liveness.
        Ensures dashboard never displays stale RUNNING status.
        """
        default_state = {
            "pid": None,
            "gateway_status": "STOPPED",
            "connection_state": "DISCONNECTED",
            "port_mode": "AUTO",
            "active_port": None,
            "device_id": "ARDUINO_SOUND_01",
            "firmware_version": "v1.3.0",
            "last_heartbeat": None,
            "last_packet_time": None,
            "packet_count": 0,
            "auto_reconnect": True,
            "message": "Gateway process is not running.",
            "is_alive": False,
        }

        state_file = settings.GATEWAY_STATE_FILE
        if not state_file.exists():
            return default_state

        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Check process liveness & heartbeat freshness
            hb_str = data.get("last_heartbeat")
            is_fresh = False
            if hb_str:
                hb_dt = datetime.strptime(hb_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                diff = (datetime.now(timezone.utc) - hb_dt).total_seconds()
                is_fresh = (diff <= 25.0)  # Heartbeat within 25 seconds

            pid = data.get("pid")
            pid_alive = False
            if pid and pid > 0:
                if sys.platform == "win32":
                    try:
                        import ctypes
                        from ctypes import wintypes
                        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                        SYNCHRONIZE = 0x00100000
                        STILL_ACTIVE = 259
                        kernel32 = ctypes.windll.kernel32
                        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
                        if h:
                            ec = wintypes.DWORD()
                            res = kernel32.GetExitCodeProcess(h, ctypes.byref(ec))
                            kernel32.CloseHandle(h)
                            pid_alive = (res != 0 and ec.value == STILL_ACTIVE)
                    except Exception:
                        pid_alive = False
                else:
                    try:
                        os.kill(pid, 0)
                        pid_alive = True
                    except (OSError, ProcessLookupError, PermissionError):
                        pid_alive = False

            if is_fresh and pid_alive and data.get("gateway_status") == "RUNNING":
                data["is_alive"] = True
                return data
            else:
                data["gateway_status"] = "STOPPED"
                data["is_alive"] = False
                data["connection_state"] = "DISCONNECTED"
                data["message"] = "Gateway process stopped or inactive."
                return data
        except Exception as e:
            logger.debug(f"Error reading gateway state: {e}")
            return default_state

    def parse_serial_line(self, raw_line: str) -> Optional[Dict[str, Any]]:
        """
        Parses structured serial CSV packet:
        Expected: UP_IOT,DEVICE_ID,SENSOR_TYPE,VALUE,UNIT,STATUS
        """
        line = raw_line.strip()
        if not line or line.startswith("#"):
            return None  # Ignore comments and empty lines

        parts = line.split(",")
        if len(parts) < 6 or parts[0] != "UP_IOT":
            err_msg = f"Malformed serial message format: '{raw_line}'"
            archiver.archive_rejected(
                event_id=None,
                source="arduino_gateway",
                source_type="REAL_HARDWARE",
                raw_payload=raw_line,
                rejection_reason=err_msg,
            )
            repository.insert_rejected_record(
                source_name="arduino_gateway",
                source_type="REAL_HARDWARE",
                raw_payload=raw_line,
                rejection_reason=err_msg,
            )
            return None

        _, dev_id, sensor_type, val_str, unit, status = parts[:6]

        if status != "OK":
            logger.warning(f"Arduino reported sensor error: {status} on {sensor_type}")
            return None

        try:
            val = float(val_str)
        except ValueError:
            err_msg = f"Invalid numeric reading: '{val_str}'"
            archiver.archive_rejected(
                event_id=None,
                source="arduino_gateway",
                source_type="REAL_HARDWARE",
                raw_payload=raw_line,
                rejection_reason=err_msg,
            )
            return None

        # Validate ADC range for analog edge sensors (SOUND_P2P, SOUND_RAW, MQ135_RAW, LDR_LIGHT)
        if sensor_type in ["SOUND_P2P", "SOUND_RAW", "MQ135_RAW", "LDR_LIGHT"]:
            if val < 0.0 or val > 1023.0:
                err_msg = f"Invalid ADC range for {sensor_type}: {val} (expected 0-1023)"
                archiver.archive_rejected(
                    event_id=None,
                    source="arduino_gateway",
                    source_type="REAL_HARDWARE",
                    raw_payload=raw_line,
                    rejection_reason=err_msg,
                )
                repository.insert_rejected_record(
                    source_name="arduino_gateway",
                    source_type="REAL_HARDWARE",
                    raw_payload=raw_line,
                    rejection_reason=err_msg,
                )
                logger.warning(err_msg)
                return None

        event_id = f"EVT_IOT_{uuid.uuid4().hex[:12].upper()}"

        return {
            "event_id": event_id,
            "device_id": dev_id,
            "sensor_type": sensor_type,
            "reading_value": val,
            "unit": unit,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "raw_reading_text": line,
            "source_type": "REAL_HARDWARE",
        }

    def process_and_persist(self, payload: Dict[str, Any]) -> bool:
        """Validates packet, archives raw data, and writes to MySQL."""
        event_id = payload["event_id"]

        # Archive raw payload
        archiver.archive_raw(
            event_id=event_id,
            source="arduino_gateway",
            payload=payload,
            source_type="REAL_HARDWARE",
        )

        # Validation
        val_rec, err = ValidationEngine.validate_iot(payload)
        if not val_rec:
            logger.warning(f"IoT payload validation rejected [{event_id}]: {err}")
            repository.insert_rejected_record(
                source_name="arduino_gateway",
                source_type="REAL_HARDWARE",
                raw_payload=payload,
                rejection_reason=err or "IoT schema validation error",
                event_id=event_id,
            )
            return False

        # Idempotent DB Write
        repository.insert_iot_reading(val_rec)
        archiver.archive_processed(event_id, "arduino_gateway", val_rec.model_dump())
        self._update_device_status("ONLINE", payload["device_id"])

        logger.info(
            f"Stored IoT Reading {event_id}: {val_rec.sensor_type} = {val_rec.reading_value} {val_rec.unit}"
        )
        # Anomaly Detection Integration (safe, non-blocking)
        try:
            from anomaly_detection.rule_engine import anomaly_engine
            anomaly_engine.check_iot_reading(val_rec.model_dump())
        except Exception as anom_err:
            logger.warning(f"IoT anomaly evaluation deferred: {anom_err}")

        return True

    def run_gateway_loop(self, max_packets: Optional[int] = None):
        """Main listening loop with auto-discovery, auto-reconnection backoff, and heartbeat."""
        logger.info(f"Starting Arduino Serial Gateway (Mode: {self.port_mode}, Config: {self.port})...")
        self.packet_count = 0
        last_log_time = 0.0

        while True:
            if not self.is_connected:
                connected = self.connect()
                if not connected:
                    curr_time = time.time()
                    if curr_time - last_log_time > 15.0:
                        logger.info(
                            f"Awaiting Arduino hardware connection on host (Mode: {self.port_mode}). Retrying in 5s..."
                        )
                        last_log_time = curr_time
                    time.sleep(5)
                    continue

            try:
                # Update heartbeat
                self.write_gateway_state(
                    gateway_status="RUNNING",
                    connection_state="STREAMING" if self.serial_conn.in_waiting > 0 else "IDLE",
                    message=f"Listening on {self.active_port}",
                )

                if self.serial_conn.in_waiting > 0:
                    raw_line = self.serial_conn.readline().decode("utf-8", errors="ignore")
                    payload = self.parse_serial_line(raw_line)
                    if payload:
                        self.process_and_persist(payload)
                        self.packet_count += 1
                        self.last_packet_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                        self.write_gateway_state(
                            gateway_status="RUNNING",
                            connection_state="STREAMING",
                            message=f"Streaming on {self.active_port}",
                            last_packet_val=payload.get("reading_value"),
                            last_packet_type=payload.get("sensor_type"),
                        )
                        if max_packets and self.packet_count >= max_packets:
                            break
                else:
                    time.sleep(0.1)
            except (serial.SerialException, OSError) as e:
                logger.warning(f"Serial connection lost on {self.active_port}: {e}. Entering auto-reconnect...")
                self.is_connected = False
                self._update_device_status("OFFLINE", self.current_device_id)
                self.write_gateway_state(
                    gateway_status="RUNNING",
                    connection_state="DISCONNECTED",
                    message=f"Connection lost on {self.active_port}: {e}",
                )
                if self.serial_conn:
                    try:
                        self.serial_conn.close()
                    except Exception:
                        pass
                self.serial_conn = None
                time.sleep(3)
            except KeyboardInterrupt:
                logger.info("Gateway stopped by user (KeyboardInterrupt).")
                break

        self.close()

    def close(self):
        self.is_connected = False
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
            except Exception:
                pass
            self.serial_conn = None
        self._update_device_status("OFFLINE", getattr(self, "current_device_id", "ARDUINO_SOUND_01"))
        self.write_gateway_state(
            gateway_status="STOPPED",
            connection_state="STOPPED",
            message="Gateway stopped cleanly.",
        )
        logger.info("Serial gateway stopped cleanly.")


serial_gateway = ArduinoSerialGateway()
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    serial_gateway.run_gateway_loop()
