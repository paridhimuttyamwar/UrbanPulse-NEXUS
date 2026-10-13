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
        self.is_custom_state_file = (state_file is not None and state_file != settings.TOMTOM_USAGE_STATE_FILE)
        self.monthly_budget = monthly_budget or settings.TOMTOM_MONTHLY_BUDGET

        if self.is_custom_state_file or self.monthly_budget <= 500:
            self.safety_margin = 0
            self.opening_balance = 0
            self.effective_limit = self.monthly_budget
        else:
            self.safety_margin = getattr(settings, "TOMTOM_SAFETY_MARGIN", 500)
            self.effective_limit = max(0, self.monthly_budget - self.safety_margin)
            self.opening_balance = getattr(settings, "TOMTOM_CONSERVATIVE_OPENING_BALANCE", 200)

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

    def _ensure_durable_table(self):
        """Ensures the api_quota_tracking table exists in the target database."""
        if self.is_custom_state_file:
            return
        try:
            from database.connection import get_db_cursor
            with get_db_cursor(commit=True) as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS api_quota_tracking (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        service_name VARCHAR(32) NOT NULL,
                        billing_month VARCHAR(7) NOT NULL,
                        requests_attempted INT NOT NULL DEFAULT 0,
                        requests_successful INT NOT NULL DEFAULT 0,
                        requests_failed INT NOT NULL DEFAULT 0,
                        last_request_at DATETIME,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        UNIQUE KEY uq_service_month (service_name, billing_month)
                    ) ENGINE=InnoDB;
                """)
        except Exception as e:
            logger.debug(f"Note on ensure_durable_table: {e}")

    def _load_durable_state(self, current_month: str) -> Optional[Dict[str, Any]]:
        """Queries durable database storage for current month quota accounting."""
        if self.is_custom_state_file:
            return None
        try:
            self._ensure_durable_table()
            from database.connection import get_db_cursor
            with get_db_cursor(commit=False) as cursor:
                cursor.execute(
                    "SELECT requests_attempted, requests_successful, requests_failed, last_request_at "
                    "FROM api_quota_tracking WHERE service_name = 'tomtom_traffic' AND billing_month = %s;",
                    (current_month,)
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "month": current_month,
                        "requests_attempted": int(row["requests_attempted"]),
                        "requests_successful": int(row["requests_successful"]),
                        "requests_failed": int(row["requests_failed"]),
                        "last_request_timestamp": str(row["last_request_at"]) if row.get("last_request_at") else None,
                    }
                return {
                    "month": current_month,
                    "requests_attempted": 0,
                    "requests_successful": 0,
                    "requests_failed": 0,
                    "last_request_timestamp": None,
                }
        except Exception as e:
            logger.error(f"Durable quota lookup failed: {e}")
            return None

    def _reserve_durable_slot(self, current_month: str) -> Tuple[bool, str, int]:
        """
        Atomically checks capacity and reserves 1 request slot in durable database storage.
        Uses pessimistic locking (SELECT ... FOR UPDATE) to ensure concurrency safety
        across multiple ephemeral GitHub runners and background worker processes.
        Returns: (reserved: bool, message: str, new_attempted_count: int)
        """
        if self.is_custom_state_file:
            return False, "Custom test state file", 0
        try:
            self._ensure_durable_table()
            from database.connection import get_db_cursor
            with get_db_cursor(commit=False) as cursor:
                conn = cursor._connection
                if getattr(conn, "autocommit", False):
                    conn.autocommit = False

                cursor.execute(
                    "SELECT requests_attempted FROM api_quota_tracking "
                    "WHERE service_name = 'tomtom_traffic' AND billing_month = %s FOR UPDATE;",
                    (current_month,)
                )
                row = cursor.fetchone()
                if not row:
                    initial_count = max(self.opening_balance, 0) + 1
                    if initial_count > self.effective_limit:
                        conn.rollback()
                        return False, f"Conservative opening balance ({self.opening_balance}) reaches effective limit ({self.effective_limit})", 0
                    cursor.execute(
                        "INSERT INTO api_quota_tracking (service_name, billing_month, requests_attempted, requests_successful, requests_failed, last_request_at) "
                        "VALUES ('tomtom_traffic', %s, %s, 0, 0, UTC_TIMESTAMP());",
                        (current_month, initial_count)
                    )
                    conn.commit()
                    return True, f"Slot {initial_count}/{self.effective_limit} reserved", initial_count

                current_count = int(row["requests_attempted"])
                if current_count < self.opening_balance:
                    current_count = self.opening_balance

                if current_count >= self.effective_limit:
                    conn.rollback()
                    msg = (
                        f"TomTom API safety cutoff engaged: {current_count}/{self.effective_limit} requests used "
                        f"(Safety margin: {self.safety_margin}, Absolute cap: {self.monthly_budget}) "
                        f"for month {current_month}. Request halted."
                    )
                    return False, msg, current_count

                new_count = current_count + 1
                cursor.execute(
                    "UPDATE api_quota_tracking SET requests_attempted = %s, last_request_at = UTC_TIMESTAMP() "
                    "WHERE service_name = 'tomtom_traffic' AND billing_month = %s;",
                    (new_count, current_month)
                )
                conn.commit()
                return True, f"Slot {new_count}/{self.effective_limit} reserved", new_count

        except Exception as e:
            try:
                if 'conn' in locals():
                    conn.rollback()
            except Exception:
                pass
            logger.error(f"Durable reservation failed: {e}")
            return False, f"Durable quota reservation error: {e}", 0

    def _record_durable_outcome(self, current_month: str, successful: bool) -> bool:
        """Atomically records request outcome (success or failure) in durable database storage."""
        if self.is_custom_state_file:
            return False
        succ = 1 if successful else 0
        fail = 0 if successful else 1
        try:
            self._ensure_durable_table()
            from database.connection import get_db_cursor
            with get_db_cursor(commit=True) as cursor:
                cursor.execute("""
                    UPDATE api_quota_tracking 
                    SET requests_successful = requests_successful + %(succ)s,
                        requests_failed = requests_failed + %(fail)s,
                        last_request_at = UTC_TIMESTAMP()
                    WHERE service_name = 'tomtom_traffic' AND billing_month = %(month)s;
                """, {"month": current_month, "succ": succ, "fail": fail})
            return True
        except Exception as e:
            logger.error(f"Failed to record durable quota outcome: {e}")
            return False

    def can_request(self) -> Tuple[bool, str]:
        """
        Non-mutating pre-flight check if capacity is available under the safety budget.
        Checks durable database first, applying safety margin and conservative opening balance.
        Fails closed in cloud mode if durable storage cannot be verified.
        """
        current_month = self._get_current_month_key()

        # 1. Check durable database storage
        durable_state = self._load_durable_state(current_month)
        if durable_state is None:
            if settings.is_cloud:
                return (
                    False,
                    f"TomTom API safety cutoff engaged: Unable to verify monthly quota from durable storage for {current_month}. Failing closed."
                )

        # 2. Reconcile with local file state and conservative opening balance
        with self._file_lock():
            local_state = self._load_state()
            local_attempted = local_state.get("requests_attempted", 0) if local_state.get("month") == current_month else 0
            durable_attempted = durable_state.get("requests_attempted", 0) if durable_state else 0
            attempted = max(local_attempted, durable_attempted, self.opening_balance)

            if attempted >= self.effective_limit:
                msg = (
                    f"TomTom API safety cutoff engaged: {attempted}/{self.effective_limit} requests used "
                    f"(Safety margin: {self.safety_margin}, Absolute cap: {self.monthly_budget}) "
                    f"for month {current_month}. Request halted."
                )
                return False, msg

            return True, "Budget available"

    def reserve_request(self) -> Tuple[bool, str]:
        """
        Atomically checks and reserves 1 request slot BEFORE issuing an HTTP request.
        Must be called for every single HTTP request attempt (including retries).
        Fails closed in cloud mode if durable storage cannot be verified.
        """
        current_month = self._get_current_month_key()

        # In cloud mode, require durable DB reservation
        if settings.is_cloud:
            ok, msg, _ = self._reserve_durable_slot(current_month)
            if not ok:
                return False, msg
            # Also update local state cache if accessible
            try:
                with self._file_lock():
                    state = self._load_state()
                    state["requests_attempted"] = max(state.get("requests_attempted", 0), self.opening_balance) + 1
                    state["last_request_timestamp"] = datetime.now(timezone.utc).isoformat()
                    self._save_state(state)
            except Exception:
                pass
            return True, msg

        # In local mode, reserve under local file lock and sync to DB
        with self._file_lock():
            local_state = self._load_state()
            local_attempted = local_state.get("requests_attempted", 0) if local_state.get("month") == current_month else 0
            
            # Reconcile with durable DB if available
            durable_state = self._load_durable_state(current_month)
            durable_attempted = durable_state.get("requests_attempted", 0) if durable_state else 0
            
            current_attempted = max(local_attempted, durable_attempted, self.opening_balance)
            if current_attempted >= self.effective_limit:
                msg = (
                    f"TomTom API safety cutoff engaged: {current_attempted}/{self.effective_limit} requests used "
                    f"(Safety margin: {self.safety_margin}, Absolute cap: {self.monthly_budget}) "
                    f"for month {current_month}. Request halted."
                )
                return False, msg

            new_attempted = current_attempted + 1
            local_state["requests_attempted"] = new_attempted
            local_state["last_request_timestamp"] = datetime.now(timezone.utc).isoformat()
            self._save_state(local_state)

            # Replicate reservation to durable DB if available
            self._reserve_durable_slot(current_month)
            return True, f"Slot {new_attempted}/{self.effective_limit} reserved"

    def record_outcome(self, successful: bool):
        """Records the outcome of an already-attempted request across durable storage and local state."""
        current_month = self._get_current_month_key()

        # 1. Update durable cloud storage atomically
        self._record_durable_outcome(current_month, successful)

        # 2. Update local state file cache with file lock
        with self._file_lock():
            state = self._load_state()
            if successful:
                state["requests_successful"] = state.get("requests_successful", 0) + 1
            else:
                state["requests_failed"] = state.get("requests_failed", 0) + 1
            state["last_request_timestamp"] = datetime.now(timezone.utc).isoformat()
            self._save_state(state)

    def record_attempt(self, successful: bool):
        """Legacy / direct attempt recording that increments attempted and outcome."""
        self.reserve_request()
        self.record_outcome(successful=successful)

    def get_usage(self) -> Dict[str, Any]:
        """Returns current accounting window usage metrics from durable storage and local cache."""
        current_month = self._get_current_month_key()
        durable_state = self._load_durable_state(current_month)

        with self._file_lock():
            local_state = self._load_state()
            local_attempted = local_state.get("requests_attempted", 0) if local_state.get("month") == current_month else 0
            durable_attempted = durable_state.get("requests_attempted", 0) if durable_state else 0
            attempted = max(local_attempted, durable_attempted, self.opening_balance)

            return {
                "month": current_month,
                "requests_attempted": attempted,
                "requests_successful": max(local_state.get("requests_successful", 0), (durable_state.get("requests_successful", 0) if durable_state else 0)),
                "requests_failed": max(local_state.get("requests_failed", 0), (durable_state.get("requests_failed", 0) if durable_state else 0)),
                "monthly_budget": self.monthly_budget,
                "safety_margin": self.safety_margin,
                "opening_balance": self.opening_balance,
                "effective_limit": self.effective_limit,
                "durable_synced": durable_state is not None,
                "last_request_timestamp": local_state.get("last_request_timestamp") or (durable_state.get("last_request_timestamp") if durable_state else None),
            }


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
            # Atomically reserve 1 request slot BEFORE issuing the HTTP request
            # Ensures failures, timeouts, and retries are strictly accounted for and cannot exceed the quota
            reserved, reserve_msg = self.budget_tracker.reserve_request()
            if not reserved:
                logger.warning(f"TomTom API request blocked by quota reservation (Attempt {attempt}/{attempts}): {reserve_msg}")
                return False, None, reserve_msg

            try:
                self.session_requests_consumed += 1
                logger.info(f"Dispatching TomTom API request (Attempt {attempt}/{attempts}, point: {latitude},{longitude}, zoom: {zoom or 10})...")
                response = requests.get(target_url, params=params, timeout=self.timeout)

                if response.status_code == 200:
                    self.budget_tracker.record_outcome(successful=True)
                    payload = response.json()
                    return True, payload, None

                # For 403 or 429, do not retry - record failure immediately
                self.budget_tracker.record_outcome(successful=False)
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
                self.budget_tracker.record_outcome(successful=False)
                last_error = f"TomTom API request timed out after {self.timeout}s."
                logger.warning(last_error)
            except requests.RequestException as e:
                self.budget_tracker.record_outcome(successful=False)
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
