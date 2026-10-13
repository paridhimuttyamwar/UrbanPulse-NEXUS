"""
UrbanPulse Rule-Based Anomaly Detection Engine.
Monitors incoming traffic, environmental, and IoT events against deterministic thresholds.
Includes cooldown-based duplicate alert suppression, reprocessing idempotency,
and persists active alerts to the MySQL anomalies table.
"""

import uuid
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import pandas as pd
from database.connection import get_db_cursor

logger = logging.getLogger(__name__)


class AnomalyRuleEngine:
    """
    Configurable Rule-Based Detection:
    1. Traffic Congestion: SEVERE congestion or avg_speed < 12 km/h on major arterial/highway.
    2. Sudden Speed Reduction: avg_speed drop below 10 km/h.
    3. Severe Air Quality: US AQI >= 150 or PM2.5 >= 60 µg/m³.
    4. Hazardous Air Quality: US AQI >= 300 or PM2.5 >= 250 µg/m³.
    5. Extreme Temperature: Temperature >= 42°C.
    6. High Winds: Wind speed >= 65 km/h.
    7. Sensor Outlier / Failure: Reading value out of physical bounds.
    """

    COOLDOWN_MINUTES: int = 60

    @classmethod
    def _insert_anomaly(
        cls,
        anomaly_type: str,
        source_type: str,
        severity: str,
        description: str,
        timestamp: datetime,
        location_id: Optional[str] = None,
        segment_id: Optional[str] = None,
        force: bool = False,
    ) -> Optional[str]:
        if not isinstance(timestamp, datetime):
            try:
                timestamp = pd.to_datetime(timestamp).to_pydatetime()
            except Exception:
                timestamp = datetime.utcnow()

        if not force:
            # 1. Reprocessing / Idempotency check: Exact same target, type, and timestamp
            check_exact_query = """
            SELECT anomaly_id FROM anomalies
            WHERE anomaly_type = %(anomaly_type)s
              AND timestamp = %(timestamp)s
              AND (
                (%(location_id)s IS NOT NULL AND location_id = %(location_id)s)
                OR
                (%(segment_id)s IS NOT NULL AND segment_id = %(segment_id)s)
              )
            LIMIT 1;
            """
            with get_db_cursor(commit=False) as cursor:
                cursor.execute(check_exact_query, {
                    "anomaly_type": anomaly_type,
                    "timestamp": timestamp,
                    "location_id": location_id,
                    "segment_id": segment_id,
                })
                existing_exact = cursor.fetchone()
                if existing_exact:
                    logger.debug(f"Reprocessed observation already logged anomaly: {existing_exact['anomaly_id']}")
                    return existing_exact["anomaly_id"]

            # 2. Cooldown check: Active alert within COOLDOWN_MINUTES
            cutoff = timestamp - timedelta(minutes=cls.COOLDOWN_MINUTES)
            check_cooldown_query = """
            SELECT anomaly_id FROM anomalies
            WHERE anomaly_type = %(anomaly_type)s
              AND status = 'ACTIVE'
              AND timestamp >= %(cutoff)s
              AND timestamp <= %(timestamp)s
              AND (
                (%(location_id)s IS NOT NULL AND location_id = %(location_id)s)
                OR
                (%(segment_id)s IS NOT NULL AND segment_id = %(segment_id)s)
              )
            LIMIT 1;
            """
            with get_db_cursor(commit=False) as cursor:
                cursor.execute(check_cooldown_query, {
                    "anomaly_type": anomaly_type,
                    "cutoff": cutoff,
                    "timestamp": timestamp,
                    "location_id": location_id,
                    "segment_id": segment_id,
                })
                existing_active = cursor.fetchone()
                if existing_active:
                    logger.info(
                        f"Alert suppressed by cooldown ({cls.COOLDOWN_MINUTES}m): "
                        f"{anomaly_type} for {location_id or segment_id} (Active alert: {existing_active['anomaly_id']})"
                    )
                    return None

        # 3. Insert new active anomaly
        anomaly_id = f"ANOM_{uuid.uuid4().hex[:12].upper()}"
        query = """
        INSERT INTO anomalies (
            anomaly_id, anomaly_type, source_type, location_id, segment_id,
            timestamp, severity, description, status
        ) VALUES (
            %(anomaly_id)s, %(anomaly_type)s, %(source_type)s, %(location_id)s, %(segment_id)s,
            %(timestamp)s, %(severity)s, %(description)s, 'ACTIVE'
        );
        """
        data = {
            "anomaly_id": anomaly_id,
            "anomaly_type": anomaly_type,
            "source_type": source_type,
            "location_id": location_id,
            "segment_id": segment_id,
            "timestamp": timestamp,
            "severity": severity,
            "description": description,
        }
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(query, data)
        logger.info(f"Anomaly detected [{severity} - {anomaly_type}]: {description} (ID: {anomaly_id})")
        return anomaly_id

    def check_traffic_reading(self, reading: Dict[str, Any], force: bool = False) -> Optional[str]:
        """
        Evaluates genuine traffic metrics for operational anomalies:
        1. Road Closure: explicitly reported by TomTom Flow data (CRITICAL).
        2. Severe Congestion: gridlock with severe LOS or speed < 12 km/h (HIGH).
        3. Significant Speed Drop: current speed reduced >= 50% below free-flow speed (MEDIUM).
        4. High Travel Delay: travel time delay >= 300 seconds above free-flow (MEDIUM / HIGH).
        Preserves source_type='REAL_API' and applies strict duplicate/cooldown suppression.
        """
        segment_id = reading.get("segment_id")
        location_id = reading.get("location_id") or "LOC_NAGPUR"
        source_type = reading.get("source_type", "REAL_API")

        avg_speed = float(reading.get("avg_speed_kmh", 0.0) or 0.0)
        free_flow_speed = float(reading.get("free_flow_speed_kmh", 0.0) or 0.0)
        current_travel_time = int(reading.get("current_travel_time_sec", 0) or 0)
        free_flow_travel_time = int(reading.get("free_flow_travel_time_sec", 0) or 0)
        road_closure = bool(reading.get("road_closure", False))
        congestion_level = str(reading.get("congestion_level", "LOW") or "LOW").upper()

        ts = reading.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = pd.to_datetime(ts).to_pydatetime()
            except Exception:
                ts = datetime.utcnow()
        elif ts is None:
            ts = datetime.utcnow()

        # Rule 1: Road Closure explicitly reported by API
        if road_closure:
            desc = (
                f"Road closure explicitly indicated by TomTom Flow telemetry for corridor {segment_id}."
            )
            return self._insert_anomaly(
                anomaly_type="ROAD_CLOSURE",
                source_type=source_type,
                severity="CRITICAL",
                description=desc,
                timestamp=ts,
                location_id=location_id,
                segment_id=segment_id,
                force=force,
            )

        # Rule 2: Severe Congestion Bottleneck
        if congestion_level == "SEVERE" or (avg_speed < 12.0 and free_flow_speed >= 25.0):
            desc = (
                f"Severe corridor gridlock detected on {segment_id}. "
                f"Observed speed {avg_speed:.1f} km/h (free-flow baseline {free_flow_speed:.1f} km/h)."
            )
            return self._insert_anomaly(
                anomaly_type="SEVERE_CONGESTION",
                source_type=source_type,
                severity="HIGH",
                description=desc,
                timestamp=ts,
                location_id=location_id,
                segment_id=segment_id,
                force=force,
            )

        # Rule 3: Significant Speed Drop below Free-Flow Speed (>= 50% drop)
        if free_flow_speed > 0:
            speed_drop_pct = max(0.0, (1.0 - (avg_speed / free_flow_speed)) * 100.0)
            if speed_drop_pct >= 50.0:
                desc = (
                    f"Significant speed reduction on {segment_id}: observed {avg_speed:.1f} km/h "
                    f"represents a {speed_drop_pct:.1f}% reduction below free-flow speed ({free_flow_speed:.1f} km/h)."
                )
                return self._insert_anomaly(
                    anomaly_type="SIGNIFICANT_SPEED_DROP",
                    source_type=source_type,
                    severity="MEDIUM",
                    description=desc,
                    timestamp=ts,
                    location_id=location_id,
                    segment_id=segment_id,
                    force=force,
                )

        # Rule 4: Unusually High Travel-Time Delay (>= 300s)
        if current_travel_time > 0 and free_flow_travel_time > 0:
            delay_sec = max(0, current_travel_time - free_flow_travel_time)
            if delay_sec >= 300:
                sev = "HIGH" if delay_sec >= 600 else "MEDIUM"
                desc = (
                    f"Unusually high travel-time delay on {segment_id}: travel time is {current_travel_time}s "
                    f"({delay_sec}s delay above {free_flow_travel_time}s free-flow baseline)."
                )
                return self._insert_anomaly(
                    anomaly_type="HIGH_TRAVEL_DELAY",
                    source_type=source_type,
                    severity=sev,
                    description=desc,
                    timestamp=ts,
                    location_id=location_id,
                    segment_id=segment_id,
                    force=force,
                )

        return None

    def check_air_quality_reading(self, reading: Dict[str, Any], force: bool = False) -> Optional[str]:
        """Evaluates atmospheric data for pollution alerts."""
        location_id = reading.get("location_id")
        us_aqi = reading.get("us_aqi")
        pm2_5 = reading.get("pm2_5")
        ts = reading.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = pd.to_datetime(ts).to_pydatetime()
            except Exception:
                ts = datetime.utcnow()
        elif ts is None:
            ts = datetime.utcnow()

        if us_aqi is not None and float(us_aqi) >= 300:
            desc = f"Hazardous air pollution spike in {location_id}! US AQI is {us_aqi}."
            return self._insert_anomaly(
                anomaly_type="HAZARDOUS_AQI",
                source_type="REAL_API",
                severity="CRITICAL",
                description=desc,
                timestamp=ts,
                location_id=location_id,
                force=force,
            )
        elif us_aqi is not None and float(us_aqi) >= 150:
            desc = f"Unhealthy air quality in {location_id}. US AQI reached {us_aqi} (PM2.5: {pm2_5} µg/m³)."
            return self._insert_anomaly(
                anomaly_type="POOR_AIR_QUALITY",
                source_type="REAL_API",
                severity="HIGH",
                description=desc,
                timestamp=ts,
                location_id=location_id,
                force=force,
            )
        elif pm2_5 is not None and float(pm2_5) >= 60.0:
            desc = f"Elevated PM2.5 concentration in {location_id}: {float(pm2_5):.1f} µg/m³."
            return self._insert_anomaly(
                anomaly_type="ELEVATED_PARTICULATES",
                source_type="REAL_API",
                severity="MEDIUM",
                description=desc,
                timestamp=ts,
                location_id=location_id,
                force=force,
            )
        return None

    def check_weather_reading(self, reading: Dict[str, Any], force: bool = False) -> Optional[str]:
        """Evaluates meteorological readings for heatwave or severe weather."""
        location_id = reading.get("location_id")
        temp_c = reading.get("temperature_c")
        wind_speed = reading.get("wind_speed_kmh")
        ts = reading.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = pd.to_datetime(ts).to_pydatetime()
            except Exception:
                ts = datetime.utcnow()
        elif ts is None:
            ts = datetime.utcnow()

        if temp_c is not None and float(temp_c) >= 42.0:
            desc = f"Extreme heatwave alert in {location_id}: Temperature reached {float(temp_c):.1f}°C."
            return self._insert_anomaly(
                anomaly_type="EXTREME_HEATWAVE",
                source_type="REAL_API",
                severity="HIGH",
                description=desc,
                timestamp=ts,
                location_id=location_id,
                force=force,
            )
        elif wind_speed is not None and float(wind_speed) >= 65.0:
            desc = f"Gale warning in {location_id}: Wind gusts recorded at {float(wind_speed):.1f} km/h."
            return self._insert_anomaly(
                anomaly_type="HIGH_WINDS",
                source_type="REAL_API",
                severity="MEDIUM",
                description=desc,
                timestamp=ts,
                location_id=location_id,
                force=force,
            )
        return None

    def check_iot_reading(self, reading: Dict[str, Any], force: bool = False) -> Optional[str]:
        """Evaluates IoT sensor values for edge anomalies."""
        device_id = reading.get("device_id")
        sensor_type = reading.get("sensor_type", "")
        val = float(reading.get("reading_value", 0))
        src_type = reading.get("source_type") or "REAL_HARDWARE"
        ts = reading.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = pd.to_datetime(ts).to_pydatetime()
            except Exception:
                ts = datetime.utcnow()
        elif ts is None:
            ts = datetime.utcnow()

        if "TEMP" in sensor_type and (val > 50.0 or val < 0.0):
            desc = f"Out-of-range sensor temperature on {device_id}: {val} {reading.get('unit')}."
            return self._insert_anomaly(
                anomaly_type="SENSOR_OUT_OF_BOUNDS",
                source_type=src_type,
                severity="HIGH",
                description=desc,
                timestamp=ts,
                force=force,
            )
        return None

    def evaluate_operational_anomalies(self, location_id: str = "LOC_NAGPUR") -> Dict[str, Any]:
        """
        Evaluates active operational anomalies for a given location or recent observations.
        Returns a summary dictionary of detected anomalies.
        """
        active_count = 0
        try:
            with get_db_cursor(commit=False) as cursor:
                cursor.execute("""
                    SELECT COUNT(*) AS cnt
                    FROM anomalies
                    WHERE status = 'ACTIVE'
                      AND timestamp >= NOW() - INTERVAL 1 HOUR;
                """)
                row = cursor.fetchone()
                if row:
                    active_count = row.get("cnt", 0)
        except Exception as e:
            logger.debug(f"Operational anomaly evaluation check error: {e}")

        return {
            "location_id": location_id,
            "anomalies_detected": active_count,
            "status": "EVALUATED",
        }


anomaly_engine = AnomalyRuleEngine()
rule_engine = anomaly_engine

