"""
UrbanPulse TomTom Traffic API Client.
Fetches real-time traffic flow telemetry from TomTom Traffic Flow Segment Data API
for configured road network corridors with strict rate safeguards, monthly budget tracking,
and schema normalization.
"""

import contextlib
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests

from config.settings import settings
from config.corridors import get_corridor_geo, NAGPUR_CORRIDORS_GEO, get_approved_corridors
from storage.raw_archiver import archiver
from validation.validator import ValidationEngine
from validation.models import TrafficRecord
from database.repository import repository

logger = logging.getLogger(__name__)


class TomTomBudgetTracker:
    """
    Process-safe, thread-safe request counter and monthly safety budget enforcer.
    Tracks requests per billing cycle month (e.g. '2026-10').
    Enforces a strict safety limit (default 16,000 / month) before contacting external servers.
    Uses atomic file-locking to protect against overlapping processes and retries.
    """

    def __init__(
        self,
        state_file: Optional[Path] = None,
        monthly_budget: Optional[int] = None,
    ):
        self.state_file = state_file or settings.TOMTOM_USAGE_STATE_FILE
        self.monthly_budget = monthly_budget or settings.TOMTOM_MONTHLY_BUDGET
        self._ensure_state_file()

    @contextlib.contextmanager
    def _file_lock(self):
        """Cross-process mutual exclusion file lock with timeout and stale-lock safety."""
        lock_path = self.state_file.with_suffix(".lock")
        start_t = time.time()
        fd = None
        while True:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                break
            except (FileExistsError, PermissionError):
                if time.time() - start_t > 5.0:
                    try:
                        if lock_path.exists() and time.time() - lock_path.stat().st_mtime > 30.0:
                            lock_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                time.sleep(0.05)
                if time.time() - start_t > 10.0:
                    logger.warning("Lock acquisition timed out, proceeding with best effort.")
                    break
        try:
            yield
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except Exception:
                    pass
                try:
                    lock_path.unlink(missing_ok=True)
                except Exception:
                    pass

    def _get_current_month_key(self) -> str:
        """Returns monthly accounting window key, e.g. '2026-10'."""
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def _ensure_state_file(self):
        """Ensures parent directory and initial state file exist."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            if not self.state_file.exists():
                self._save_state({
                    "month": self._get_current_month_key(),
                    "requests_attempted": 0,
                    "requests_successful": 0,
                    "requests_failed": 0,
                    "last_request_timestamp": None,
                    "monthly_budget": self.monthly_budget,
                })
        except Exception as e:
            logger.warning(f"Could not initialize TomTom budget state file: {e}")

    def _load_state(self) -> Dict[str, Any]:
        """Loads state dictionary with automatic monthly rollover."""
        current_month = self._get_current_month_key()
        default_state = {
            "month": current_month,
            "requests_attempted": 0,
            "requests_successful": 0,
            "requests_failed": 0,
            "last_request_timestamp": None,
            "monthly_budget": self.monthly_budget,
        }
        if not self.state_file.exists():
            return default_state

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Automatic rollover if month changed
            if data.get("month") != current_month:
                logger.info(f"TomTom budget rollover: previous {data.get('month')} -> new {current_month}")
                data = default_state
                self._save_state(data)
            return data
        except Exception as e:
            logger.warning(f"Error reading TomTom state file: {e}")
            return default_state

    def _save_state(self, state: Dict[str, Any]):
        """Persists state atomically via temporary file replacement."""
        try:
            temp_file = self.state_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            temp_file.replace(self.state_file)
        except Exception as e:
            logger.warning(f"Failed to persist TomTom usage state: {e}")

    def can_request(self) -> Tuple[bool, str]:
        """Checks if another HTTP request is permitted under safety budget with lock."""
        with self._file_lock():
            state = self._load_state()
            attempted = state.get("requests_attempted", 0)
            budget = state.get("monthly_budget", self.monthly_budget)

            if attempted >= budget:
                msg = (
                    f"TomTom API safety cutoff engaged: {attempted}/{budget} requests used "
                    f"for month {state.get('month')}. Request halted."
                )
                return False, msg
            return True, "Budget available"

    def record_attempt(self, successful: bool):
        """Records an attempted HTTP request and its outcome with process lock."""
        with self._file_lock():
            state = self._load_state()
            state["requests_attempted"] = state.get("requests_attempted", 0) + 1
            if successful:
                state["requests_successful"] = state.get("requests_successful", 0) + 1
            else:
                state["requests_failed"] = state.get("requests_failed", 0) + 1
            state["last_request_timestamp"] = datetime.now(timezone.utc).isoformat()
            self._save_state(state)

    def get_usage(self) -> Dict[str, Any]:
        """Returns current accounting window usage metrics."""
        with self._file_lock():
            return self._load_state()


class TomTomTrafficClient:
    """
    Client for TomTom Traffic Flow Segment Data API.
    
    Adheres strictly to the UrbanPulse Real-Data-Only policy:
    - Never fabricates unmeasured metrics (vehicle counts, densities).
    - Preserves exact speed and travel time measurements from TomTom.
    - Classifies congestion level based on genuine observed speed vs free-flow speed.
    - Strictly archives raw response to JSONL for data provenance.
    - Idempotently loads normalized records with source_type='REAL_API'.
    - Enforces local monthly request quota safeguards.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.TOMTOM_API_KEY
        self.base_url = settings.TOMTOM_TRAFFIC_FLOW_BASE_URL
        self.timeout = settings.API_TIMEOUT_SECONDS
        self.max_retries = settings.API_MAX_RETRIES
        self.budget_tracker = TomTomBudgetTracker()
        # Session-level request counter
        self.session_requests_consumed = 0

    @property
    def requests_consumed(self) -> int:
        """Total requests consumed across all sessions from persistent state."""
        return self.budget_tracker.get_usage().get("requests_attempted", 0)

    def _generate_event_id(self, segment_id: str, timestamp_str: str) -> str:
        """Generates deterministic unique event ID for duplicate prevention."""
        hash_input = f"TOMTOM_TRAFFIC_{segment_id}_{timestamp_str}"
        digest = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:16]
        return f"EVT_TRF_TOMTOM_{digest.upper()}"

    def calculate_congestion_level(self, current_speed: float, free_flow_speed: float) -> str:
        """
        Derives Level of Service (LOS) / congestion level from real speed measurements.
        Ratio of current speed to free-flow baseline:
        - >= 0.75: LOW (Free flow / nominal)
        - 0.50 - 0.74: MEDIUM (Moderate friction)
        - 0.30 - 0.49: HIGH (Substantial bottleneck)
        - < 0.30: SEVERE (Severe gridlock / crawl)
        """
        if free_flow_speed <= 0:
            return "LOW"
        speed_ratio = current_speed / free_flow_speed
        if speed_ratio >= 0.75:
            return "LOW"
        elif speed_ratio >= 0.50:
            return "MEDIUM"
        elif speed_ratio >= 0.30:
            return "HIGH"
        else:
            return "SEVERE"

    def fetch_flow_segment_data(
        self, latitude: float, longitude: float, unit: str = "KMPH", zoom: Optional[int] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Calls TomTom Flow Segment Data API for given coordinates and zoom level.
        Checks monthly safety budget BEFORE issuing HTTP request.
        Counts every attempt against persistent budget state.
        Returns: (success, payload_or_none, error_message_or_none)
        """
        if not self.api_key:
            err = "TOMTOM_API_KEY is not configured in environment."
            logger.error(err)
            return False, None, err

        # Check safety budget first
        allowed, budget_msg = self.budget_tracker.can_request()
        if not allowed:
            logger.error(budget_msg)
            return False, None, budget_msg

        params = {
            "point": f"{latitude},{longitude}",
            "unit": unit,
            "key": self.api_key,
        }

        # Format URL with corridor zoom level if provided
        target_url = self.base_url
        if zoom is not None:
            target_url = re.sub(r"/\d+/json", f"/{int(zoom)}/json", self.base_url)

        # Safe single attempt with at most 1 retry on transient network error
        attempts = min(2, self.max_retries)
        last_error = None

        for attempt in range(1, attempts + 1):
            # Budget check before retry
            if attempt > 1:
                allowed, budget_msg = self.budget_tracker.can_request()
                if not allowed:
                    return False, None, budget_msg

            try:
                self.session_requests_consumed += 1
                logger.info(f"Dispatching TomTom API request (Attempt {attempt}/{attempts}, point: {latitude},{longitude}, zoom: {zoom or 10})...")
                response = requests.get(target_url, params=params, timeout=self.timeout)

                if response.status_code == 200:
                    self.budget_tracker.record_attempt(successful=True)
                    payload = response.json()
                    return True, payload, None

                # For 403 or 429, do not retry - record failure immediately
                self.budget_tracker.record_attempt(successful=False)
                if response.status_code == 403:
                    last_error = "TomTom API Authentication Error 403: Forbidden or invalid API key."
                    logger.error(last_error)
                    return False, None, last_error
                elif response.status_code == 429:
                    last_error = "TomTom API Rate Limit 429: Provider quota or QPS limit exceeded."
                    logger.error(last_error)
                    return False, None, last_error
                else:
                    last_error = f"TomTom API HTTP {response.status_code}: {response.text[:200]}"
                    logger.warning(last_error)

            except requests.Timeout:
                self.budget_tracker.record_attempt(successful=False)
                last_error = f"TomTom API request timed out after {self.timeout}s."
                logger.warning(last_error)
            except requests.RequestException as e:
                self.budget_tracker.record_attempt(successful=False)
                last_error = f"TomTom API network connection error: {str(e)}"
                logger.warning(last_error)

            if attempt < attempts:
                time.sleep(2.0)

        return False, None, last_error

    def normalize_flow_response(
        self, raw_payload: Dict[str, Any], segment_id: str
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Extracts genuine measurements from TomTom response into normalized dictionary.
        Does NOT fabricate vehicle counts or densities (kept as None).
        """
        flow_data = raw_payload.get("flowSegmentData")
        if not flow_data:
            return False, None, "Response missing 'flowSegmentData' object."

        corridor_info = get_corridor_geo(segment_id)
        if not corridor_info:
            return False, None, f"Segment '{segment_id}' not found in corridor geographic registry."

        # Extract genuine fields with safe fallbacks for missing attributes
        current_speed = flow_data.get("currentSpeed")
        free_flow_speed = flow_data.get("freeFlowSpeed")
        current_travel_time = flow_data.get("currentTravelTime")
        free_flow_travel_time = flow_data.get("freeFlowTravelTime")
        confidence = flow_data.get("confidence")
        road_closure = flow_data.get("roadClosure", False)

        if current_speed is None:
            return False, None, "TomTom response missing required 'currentSpeed' measurement."

        current_speed = float(current_speed)
        free_flow_speed = float(free_flow_speed) if free_flow_speed is not None else float(corridor_info["speed_limit_kmh"])

        # Congestion level derived strictly from observed speeds
        congestion = self.calculate_congestion_level(current_speed, free_flow_speed)

        # Standard UTC timestamp
        now_utc = datetime.now(timezone.utc)
        ts_str = now_utc.strftime("%Y-%m-%d %H:%M:%S")
        event_id = self._generate_event_id(segment_id, ts_str)

        normalized = {
            "event_id": event_id,
            "sensor_id": corridor_info["sensor_id"],
            "segment_id": segment_id,
            "timestamp": now_utc,
            # Genuinely unmeasured attributes are explicitly None
            "vehicle_count": None,
            "traffic_density_vpk": None,
            # Genuine TomTom flow measurements
            "avg_speed_kmh": round(current_speed, 2),
            "free_flow_speed_kmh": round(free_flow_speed, 2),
            "current_travel_time_sec": int(current_travel_time) if current_travel_time is not None else None,
            "free_flow_travel_time_sec": int(free_flow_travel_time) if free_flow_travel_time is not None else None,
            "confidence_score": round(float(confidence), 3) if confidence is not None else None,
            "road_closure": bool(road_closure),
            "congestion_level": congestion,
            "source_type": "REAL_API",
        }

        return True, normalized, None

    def ingest_segment(
        self, segment_id: str
    ) -> Tuple[bool, Optional[TrafficRecord], Optional[str]]:
        """
        Executes a single controlled real-data ingestion cycle for a road segment:
        1. Look up verified corridor coordinates.
        2. Query live TomTom Flow API (with budget check).
        3. Archive raw response payload to disk (data/raw/).
        4. Normalize without fabricating missing measurements.
        5. Validate schema with ValidationEngine.
        6. Persist to MySQL traffic_readings with source_type='REAL_API'.
        7. Archive processed record (data/processed/).
        """
        corridor = get_corridor_geo(segment_id)
        if not corridor:
            err = f"Unrecognized road corridor ID: {segment_id}"
            logger.error(err)
            return False, None, err

        lat = corridor["latitude"]
        lon = corridor["longitude"]
        zoom = corridor.get("zoom")

        # 1. Live Fetch
        ok, raw_payload, fetch_err = self.fetch_flow_segment_data(lat, lon, zoom=zoom)
        if not ok or not raw_payload:
            return False, None, f"TomTom API request failed for {segment_id}: {fetch_err}"

        # 2. Archive Raw Payload
        timestamp_slug = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        temp_event_id = self._generate_event_id(segment_id, timestamp_slug)
        archiver.archive_raw(
            event_id=temp_event_id,
            source="tomtom_traffic_flow",
            payload=raw_payload,
            source_type="REAL_API",
        )

        # 3. Normalize Response
        norm_ok, norm_dict, norm_err = self.normalize_flow_response(raw_payload, segment_id)
        if not norm_ok or not norm_dict:
            return False, None, f"Normalization error for {segment_id}: {norm_err}"

        # 4. Validate with Pydantic
        record, val_err = ValidationEngine.validate_traffic(
            norm_dict, source_name="tomtom_client", source_type="REAL_API"
        )
        if not record:
            return False, None, f"Validation failure for {segment_id}: {val_err}"

        # 5. Persist to MySQL
        try:
            repository.insert_traffic_reading(record)
            archiver.archive_processed(
                event_id=record.event_id,
                source="tomtom_client",
                record_data=record.model_dump(),
            )
            logger.info(
                f"Successfully ingested genuine TomTom reading for {segment_id} "
                f"[{record.avg_speed_kmh} km/h, LOS: {record.congestion_level}, Event: {record.event_id}]"
            )
        except Exception as e:
            db_err = f"Database persistence failure for {segment_id}: {str(e)}"
            logger.error(db_err)
            return False, None, db_err

        # 6. Evaluate Operational Traffic Anomalies (Idempotent)
        try:
            from anomaly_detection.rule_engine import rule_engine
            anomaly_id = rule_engine.check_traffic_reading(record.model_dump())
            if anomaly_id:
                logger.info(f"Operational traffic anomaly registered for {segment_id}: {anomaly_id}")
        except Exception as anom_err:
            logger.warning(f"Anomaly evaluation bypassed for {segment_id}: {anom_err}")

        return True, record, None

    def ingest_all_corridors(
        self, corridor_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Ingests real-time observations for approved corridors (default: verified corridors).
        Processes each corridor independently so that failure on one segment does not
        block others. Respects monthly safety budget throughout batch execution.
        """
        targets = corridor_ids if corridor_ids is not None else get_approved_corridors()
        logger.info(f"Starting TomTom real-data ingestion cycle for {len(targets)} corridors...")

        results = {
            "total_corridors": len(targets),
            "successful": 0,
            "failed": 0,
            "successful_segments": [],
            "failed_segments": {},
            "records": [],
            "budget_usage": self.budget_tracker.get_usage(),
        }

        for sid in targets:
            # Check budget before attempting segment
            allowed, b_msg = self.budget_tracker.can_request()
            if not allowed:
                logger.warning(f"Stopping batch ingestion: {b_msg}")
                results["failed_segments"][sid] = b_msg
                results["failed"] += 1
                continue

            success, rec, err = self.ingest_segment(sid)
            if success and rec:
                results["successful"] += 1
                results["successful_segments"].append(sid)
                results["records"].append(rec)
            else:
                results["failed"] += 1
                results["failed_segments"][sid] = err or "Unknown ingestion error"

        results["budget_usage"] = self.budget_tracker.get_usage()
        logger.info(
            f"TomTom cycle finished: {results['successful']}/{len(targets)} succeeded, "
            f"{results['failed']} failed. Total monthly usage: {results['budget_usage']['requests_attempted']}."
        )
        return results


tomtom_client = TomTomTrafficClient()
