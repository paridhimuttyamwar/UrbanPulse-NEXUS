"""
UrbanPulse Dashboard Data Loader.
Provides cached database access methods for dashboard views.
Uses short TTL (30s) to keep views fresh while preventing repetitive queries.
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
import streamlit as st

from database.connection import get_db_cursor

logger = logging.getLogger(__name__)


@st.cache_data(ttl=30)
def load_locations() -> pd.DataFrame:
    query = """
    SELECT location_id, city_name, state_name, latitude, longitude 
    FROM locations 
    ORDER BY CASE WHEN location_id = 'LOC_NAGPUR' THEN 0 ELSE 1 END, city_name ASC
    """
    with get_db_cursor(commit=False) as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ["latitude", "longitude"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=30)
def load_road_segments(location_id: Optional[str] = None) -> pd.DataFrame:
    query = """
    SELECT segment_id, location_id, road_name, segment_type, speed_limit_kmh, capacity_vph, length_km
    FROM road_segments
    """
    params = {}
    if location_id and location_id != "ALL":
        query += " WHERE location_id = %(loc)s"
        params["loc"] = location_id
    query += " ORDER BY road_name"
    with get_db_cursor(commit=False) as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ["speed_limit_kmh", "capacity_vph", "length_km"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=20)
def load_latest_weather(location_id: Optional[str] = None) -> pd.DataFrame:
    query = """
    SELECT w.location_id, l.city_name, w.timestamp, w.temperature_c, w.relative_humidity_pct,
           w.wind_speed_kmh, w.precipitation_mm, w.weather_condition, w.weather_code, w.source_type
    FROM weather_readings w
    JOIN locations l ON w.location_id = l.location_id
    WHERE w.timestamp = (
        SELECT MAX(w2.timestamp) FROM weather_readings w2 WHERE w2.location_id = w.location_id
    )
    """
    params = {}
    if location_id and location_id != "ALL":
        query += " AND w.location_id = %(loc)s"
        params["loc"] = location_id
    query += " ORDER BY l.city_name;"
    with get_db_cursor(commit=False) as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ["temperature_c", "relative_humidity_pct", "wind_speed_kmh", "precipitation_mm", "weather_code"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=20)
def load_latest_air_quality(location_id: Optional[str] = None) -> pd.DataFrame:
    query = """
    SELECT a.location_id, l.city_name, a.timestamp, a.pm2_5, a.pm10,
           a.nitrogen_dioxide, a.ozone, a.carbon_monoxide, a.us_aqi,
           a.european_aqi, a.aqi_category, a.source_type
    FROM air_quality_readings a
    JOIN locations l ON a.location_id = l.location_id
    WHERE a.timestamp = (
        SELECT MAX(a2.timestamp) FROM air_quality_readings a2 WHERE a2.location_id = a.location_id
    )
    """
    params = {}
    if location_id and location_id != "ALL":
        query += " AND a.location_id = %(loc)s"
        params["loc"] = location_id
    query += " ORDER BY l.city_name;"
    with get_db_cursor(commit=False) as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ["pm2_5", "pm10", "nitrogen_dioxide", "ozone", "carbon_monoxide", "us_aqi", "european_aqi"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=20)
def load_traffic_readings(
    segment_id: Optional[str] = None,
    location_id: Optional[str] = None,
    start_date: Optional[Any] = None,
    end_date: Optional[Any] = None,
    source_type: Optional[str] = "REAL_API",
    limit: int = 2000,
) -> pd.DataFrame:
    from datetime import date, time
    query = """
    SELECT t.event_id, t.sensor_id, t.segment_id, r.road_name, r.segment_type,
           r.speed_limit_kmh, r.length_km, r.capacity_vph, r.location_id, l.city_name,
           t.timestamp, t.vehicle_count, t.avg_speed_kmh, t.free_flow_speed_kmh,
           t.current_travel_time_sec, t.free_flow_travel_time_sec, t.confidence_score,
           t.road_closure, t.congestion_level, t.traffic_density_vpk, t.source_type
    FROM traffic_readings t
    JOIN road_segments r ON t.segment_id = r.segment_id
    JOIN locations l ON r.location_id = l.location_id
    WHERE 1=1
    """
    params: Dict[str, Any] = {"limit": limit}
    if source_type and source_type != "ALL":
        query += " AND t.source_type = %(source_type)s"
        params["source_type"] = source_type
    if segment_id and segment_id != "ALL":
        query += " AND t.segment_id = %(segment_id)s"
        params["segment_id"] = segment_id
    if location_id and location_id != "ALL":
        query += " AND r.location_id = %(location_id)s"
        params["location_id"] = location_id

    if start_date:
        if isinstance(start_date, datetime):
            s_dt = start_date
        elif isinstance(start_date, date):
            s_dt = datetime.combine(start_date, time.min)
        else:
            s_dt = pd.to_datetime(start_date).to_pydatetime()
        query += " AND TIMESTAMPADD(MINUTE, 330, t.timestamp) >= %(start_dt)s"
        params["start_dt"] = s_dt

    if end_date:
        if isinstance(end_date, datetime):
            e_dt = end_date
        elif isinstance(end_date, date):
            e_dt = datetime.combine(end_date, time.max)
        else:
            e_dt = pd.to_datetime(end_date).to_pydatetime()
        query += " AND TIMESTAMPADD(MINUTE, 330, t.timestamp) <= %(end_dt)s"
        params["end_dt"] = e_dt

    query += " ORDER BY t.timestamp DESC LIMIT %(limit)s"

    with get_db_cursor(commit=False) as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["timestamp_ist"] = df["timestamp"].dt.tz_localize("UTC").dt.tz_convert("Asia/Kolkata")
    df["timestamp_ist_naive"] = df["timestamp_ist"].dt.tz_localize(None)
    df["timestamp_display"] = df["timestamp_ist"].dt.strftime("%d %b %Y, %I:%M:%S %p IST")

    for col in [
        "vehicle_count", "avg_speed_kmh", "free_flow_speed_kmh",
        "current_travel_time_sec", "free_flow_travel_time_sec",
        "confidence_score", "traffic_density_vpk", "speed_limit_kmh",
        "length_km", "capacity_vph"
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "road_closure" in df.columns:
        df["road_closure"] = df["road_closure"].astype(bool)

    # Derived delay: max(0, current_travel_time - free_flow_travel_time) preserving missing as NaN
    if "current_travel_time_sec" in df.columns and "free_flow_travel_time_sec" in df.columns:
        def _calc_delay(row):
            cur = row.get("current_travel_time_sec")
            ff = row.get("free_flow_travel_time_sec")
            if pd.isna(cur) or pd.isna(ff):
                return None
            try:
                return max(0, int(round(float(cur) - float(ff))))
            except (ValueError, TypeError):
                return None

        df["delay_seconds"] = df.apply(_calc_delay, axis=1)
    else:
        df["delay_seconds"] = None

    # Derived speed reduction percentage: max(0, (free_flow_speed - avg_speed) / free_flow_speed * 100) preserving missing as NaN
    def _calc_reduction(row):
        cur = row.get("avg_speed_kmh")
        ff = row.get("free_flow_speed_kmh")
        if pd.isna(cur) or pd.isna(ff):
            return None
        try:
            cur_f = float(cur)
            ff_f = float(ff)
            if ff_f <= 0:
                return None
            return max(0.0, ((ff_f - cur_f) / ff_f) * 100.0)
        except (ZeroDivisionError, TypeError, ValueError):
            return None

    df["speed_reduction_pct"] = df.apply(_calc_reduction, axis=1)
    return df


@st.cache_data(ttl=20)
def load_latest_traffic_per_corridor(
    location_id: Optional[str] = "LOC_NAGPUR",
    source_type: Optional[str] = "REAL_API",
    stale_threshold_minutes: int = 90,
) -> pd.DataFrame:
    """
    Loads the single latest traffic observation per corridor matching location and source_type.
    Computes data freshness status (FRESH vs STALE) based on elapsed time from current UTC.
    """
    query = """
    SELECT t.id, t.event_id, t.sensor_id, t.segment_id, r.road_name, r.segment_type,
           r.speed_limit_kmh, r.length_km, r.capacity_vph, r.location_id, l.city_name,
           t.timestamp, t.vehicle_count, t.avg_speed_kmh, t.free_flow_speed_kmh,
           t.current_travel_time_sec, t.free_flow_travel_time_sec, t.confidence_score,
           t.road_closure, t.congestion_level, t.traffic_density_vpk, t.source_type
    FROM traffic_readings t
    JOIN road_segments r ON t.segment_id = r.segment_id
    JOIN locations l ON r.location_id = l.location_id
    JOIN (
        SELECT segment_id, MAX(id) AS max_id
        FROM traffic_readings
        WHERE 1=1
    """
    params: Dict[str, Any] = {}
    if source_type and source_type != "ALL":
        query += " AND source_type = %(source_type)s"
        params["source_type"] = source_type
    query += """
        GROUP BY segment_id
    ) latest ON t.id = latest.max_id
    WHERE 1=1
    """
    if location_id and location_id != "ALL":
        query += " AND r.location_id = %(location_id)s"
        params["location_id"] = location_id

    query += " ORDER BY r.segment_id ASC"

    with get_db_cursor(commit=False) as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["timestamp_ist"] = df["timestamp"].dt.tz_localize("UTC").dt.tz_convert("Asia/Kolkata")
    df["timestamp_ist_naive"] = df["timestamp_ist"].dt.tz_localize(None)
    df["timestamp_display"] = df["timestamp_ist"].dt.strftime("%d %b %Y, %I:%M:%S %p IST")

    for col in [
        "vehicle_count", "avg_speed_kmh", "free_flow_speed_kmh",
        "current_travel_time_sec", "free_flow_travel_time_sec",
        "confidence_score", "traffic_density_vpk", "speed_limit_kmh",
        "length_km", "capacity_vph"
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "road_closure" in df.columns:
        df["road_closure"] = df["road_closure"].astype(bool)

    # Derived delay: max(0, current_travel_time - free_flow_travel_time) preserving missing as NaN
    if "current_travel_time_sec" in df.columns and "free_flow_travel_time_sec" in df.columns:
        def _calc_delay_latest(row):
            cur = row.get("current_travel_time_sec")
            ff = row.get("free_flow_travel_time_sec")
            if pd.isna(cur) or pd.isna(ff):
                return None
            try:
                return max(0, int(round(float(cur) - float(ff))))
            except (ValueError, TypeError):
                return None

        df["delay_seconds"] = df.apply(_calc_delay_latest, axis=1)
    else:
        df["delay_seconds"] = None

    # Derived speed reduction percentage: max(0, (free_flow_speed - avg_speed) / free_flow_speed * 100) preserving missing as NaN
    def _calc_red_latest(row):
        spd = row.get("avg_speed_kmh")
        ff = row.get("free_flow_speed_kmh")
        if pd.isna(spd) or pd.isna(ff):
            return None
        try:
            spd_f = float(spd)
            ff_f = float(ff)
            if ff_f <= 0:
                return None
            return max(0.0, ((ff_f - spd_f) / ff_f) * 100.0)
        except (ZeroDivisionError, TypeError, ValueError):
            return None

    df["speed_reduction_pct"] = df.apply(_calc_red_latest, axis=1)

    # Compute data freshness relative to current UTC
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    def _calc_fresh(ts):
        if pd.isna(ts):
            return "NO DATA", True, "Never", 999999.0
        diff_sec = (now_utc - ts).total_seconds()
        mins = int(diff_sec // 60)
        hours = diff_sec / 3600.0
        time_ago = f"{mins}m ago" if mins < 60 else (f"{hours:.1f}h ago" if hours < 24 else f"{int(diff_sec // 86400)}d ago")
        is_stale = diff_sec > (stale_threshold_minutes * 60)
        badge = f"STALE ({time_ago})" if is_stale else f"FRESH ({time_ago})"
        return badge, is_stale, time_ago, diff_sec

    fresh_tuples = df["timestamp"].apply(_calc_fresh)
    df["freshness_badge"] = [f[0] for f in fresh_tuples]
    df["is_stale"] = [f[1] for f in fresh_tuples]
    df["time_ago"] = [f[2] for f in fresh_tuples]
    df["elapsed_seconds"] = [f[3] for f in fresh_tuples]

    return df


@st.cache_data(ttl=20)
def load_anomalies(
    status: Optional[str] = None,
    location_id: Optional[str] = None,
    source_type: Optional[str] = "REAL_API",
    limit: int = 100
) -> pd.DataFrame:
    query = """
    SELECT a.anomaly_id, a.anomaly_type, a.source_type, a.location_id, a.segment_id,
           r.road_name, a.timestamp, a.severity, a.description, a.status,
           a.resolution_notes, a.resolved_at, a.created_at
    FROM anomalies a
    LEFT JOIN road_segments r ON a.segment_id = r.segment_id
    WHERE 1=1
    """
    params: Dict[str, Any] = {"limit": limit}
    if status and status != "ALL":
        query += " AND a.status = %(status)s"
        params["status"] = status
    if source_type and source_type != "ALL":
        query += " AND a.source_type = %(source_type)s"
        params["source_type"] = source_type
    else:
        query += " AND a.source_type != 'TEST_MOCK'"
    if location_id and location_id != "ALL":
        query += """ AND (
            a.location_id = %(loc)s 
            OR a.segment_id IN (SELECT r.segment_id FROM road_segments r WHERE r.location_id = %(loc)s)
        )"""
        params["loc"] = location_id

    query += " ORDER BY a.timestamp DESC LIMIT %(limit)s"

    with get_db_cursor(commit=False) as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
    if not rows:
        return pd.DataFrame(columns=[
            "anomaly_id", "anomaly_type", "source_type", "location_id", "segment_id",
            "road_name", "timestamp", "severity", "description", "status",
            "resolution_notes", "resolved_at", "created_at",
            "timestamp_ist", "timestamp_display"
        ])
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["timestamp_ist"] = df["timestamp"].dt.tz_localize("UTC").dt.tz_convert("Asia/Kolkata")
    df["timestamp_display"] = df["timestamp_ist"].dt.strftime("%d %b %Y, %I:%M:%S %p IST")
    if "resolved_at" in df.columns:
        df["resolved_at"] = pd.to_datetime(df["resolved_at"])
    return df


@st.cache_data(ttl=15)
def load_iot_devices(device_type: Optional[str] = None) -> List[Dict[str, Any]]:
    query = """
    SELECT device_id, device_name, device_model, device_type,
           location_id, connected_sensors, port_assignment,
           status, last_heartbeat, created_at
    FROM iot_devices
    WHERE 1=1
    """
    params = {}
    if device_type and device_type != "ALL":
        query += " AND device_type = %(dtype)s"
        params["dtype"] = device_type
    query += " ORDER BY device_id"
    with get_db_cursor(commit=False) as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
    return rows if rows else []


@st.cache_data(ttl=15)
def load_iot_readings(
    device_id: Optional[str] = None,
    location_id: Optional[str] = None,
    source_type: Optional[str] = None,
    sensor_type: Optional[str] = None,
    time_window_minutes: Optional[int] = None,
    limit: int = 500,
) -> pd.DataFrame:
    query = """
    SELECT s.id, s.event_id, s.device_id, s.sensor_type, s.reading_value, s.unit,
           s.timestamp, s.raw_reading_text, s.source_type
    FROM iot_sensor_readings s
    JOIN iot_devices d ON s.device_id = d.device_id
    WHERE 1=1
    """
    params: Dict[str, Any] = {"limit": limit}
    if device_id and device_id != "ALL":
        query += " AND s.device_id = %(dev)s"
        params["dev"] = device_id
    if location_id and location_id != "ALL":
        query += " AND d.location_id = %(loc)s"
        params["loc"] = location_id
    if source_type and source_type != "ALL":
        query += " AND s.source_type = %(src)s"
        params["src"] = source_type
    if sensor_type and sensor_type != "ALL":
        query += " AND s.sensor_type = %(stype)s"
        params["stype"] = sensor_type
    if time_window_minutes and time_window_minutes > 0:
        query += " AND s.timestamp >= UTC_TIMESTAMP() - INTERVAL %(mins)s MINUTE"
        params["mins"] = time_window_minutes
    query += " ORDER BY s.timestamp DESC LIMIT %(limit)s"

    with get_db_cursor(commit=False) as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # Stored timestamps are UTC in MySQL. Localize to UTC and convert to Asia/Kolkata (IST):
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["timestamp_ist"] = df["timestamp"].dt.tz_localize("UTC").dt.tz_convert("Asia/Kolkata")
    df["timestamp_ist_naive"] = df["timestamp_ist"].dt.tz_localize(None)
    df["timestamp_display"] = df["timestamp_ist"].dt.strftime("%d %b %Y, %I:%M:%S %p IST")
    df["reading_value"] = pd.to_numeric(df["reading_value"], errors="coerce")
    return df


def get_gateway_runtime_status() -> Dict[str, Any]:
    """Retrieves live background gateway process state without touching the serial port."""
    from iot.serial_gateway.gateway import ArduinoSerialGateway
    return ArduinoSerialGateway.get_gateway_status()


@st.cache_data(ttl=30)
def load_pipeline_runs(limit: int = 20) -> pd.DataFrame:
    query = """
    SELECT run_id, pipeline_name, status, records_processed, records_rejected,
           started_at, finished_at, error_message
    FROM pipeline_runs
    ORDER BY started_at DESC
    LIMIT %(limit)s;
    """
    with get_db_cursor(commit=False) as cursor:
        cursor.execute(query, {"limit": limit})
        rows = cursor.fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ["records_processed", "records_rejected"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def format_time_ago(dt: Optional[datetime], is_utc: bool = False) -> Tuple[str, Optional[float]]:
    """
    Computes elapsed seconds and a human-readable elapsed time string,
    reconciling UTC payload timestamps (traffic/IoT) vs IST local timestamps (weather/AQ).
    Returns (human_str, elapsed_seconds).
    """
    if dt is None:
        return "Never", None

    if is_utc:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        now = datetime.now()

    diff = (now - dt).total_seconds()
    if diff < 0:
        return "Just now", 0.0

    mins = int(diff // 60)
    hours = diff / 3600.0
    days = int(diff // 86400)

    if mins < 1:
        return "Just now", diff
    elif mins < 60:
        return f"{mins}m ago", diff
    elif hours < 24:
        return f"{hours:.1f}h ago", diff
    else:
        return f"{days}d ago", diff


def trigger_manual_environmental_ingestion(location_id: str = "LOC_NAGPUR") -> Dict[str, Any]:
    """
    Safely triggers on-demand ingestion for Nagpur weather and air quality.
    Reuses existing WeatherIngestionClient and AirQualityIngestionClient.
    Clears Streamlit data caches upon success so UI reflects new records.
    Returns dict with success, message, and insertion statuses.
    """
    try:
        from ingestion.weather.weather_client import weather_client
        from ingestion.air_quality.air_quality_client import air_quality_client

        w_ok = weather_client.ingest_primary_city()
        aq_ok = air_quality_client.ingest_primary_city()

        if w_ok or aq_ok:
            st.cache_data.clear()
            msg = "Successfully synchronized live Open-Meteo observations for Nagpur."
            return {
                "success": True,
                "message": msg,
                "weather_inserted": "OK" if w_ok else "Deferred",
                "aq_inserted": "OK" if aq_ok else "Deferred",
                "error": None,
            }
        else:
            return {
                "success": False,
                "message": "API ingestion returned no new records or encountered upstream timeout.",
                "weather_inserted": "Failed",
                "aq_inserted": "Failed",
                "error": "Upstream timeout or validation failure",
            }
    except Exception as e:
        logger.error(f"Manual environmental ingestion failed: {e}")
        return {
            "success": False,
            "message": f"Ingestion error: {str(e)}",
            "weather_inserted": "Error",
            "aq_inserted": "Error",
            "error": str(e),
        }


@st.cache_data(ttl=20)
def load_data_source_status() -> List[Dict[str, Any]]:
    """Checks the health, row count, observation freshness, and pipeline status for each data source."""
    with get_db_cursor(commit=False) as cursor:
        cursor.execute("SELECT COUNT(*) AS c, MAX(timestamp) AS last_ts FROM weather_readings")
        w_res = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) AS c, MAX(timestamp) AS last_ts FROM air_quality_readings")
        aq_res = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) AS c, MAX(timestamp) AS last_ts FROM traffic_readings WHERE source_type = 'REAL_API'")
        trf_res = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) AS c, MAX(timestamp) AS last_ts FROM iot_sensor_readings")
        iot_res = cursor.fetchone()

    # Weather: local IST, 75 min freshness threshold
    w_str, w_sec = format_time_ago(w_res["last_ts"], is_utc=False)
    if w_res["c"] == 0 or w_sec is None:
        w_status = "NO DATA"
    elif w_sec <= 4500:
        w_status = f"FRESH ({w_str})"
    else:
        w_status = f"STALE ({w_str})"

    # Air Quality: local IST, 90 min freshness threshold
    aq_str, aq_sec = format_time_ago(aq_res["last_ts"], is_utc=False)
    if aq_res["c"] == 0 or aq_sec is None:
        aq_status = "NO DATA"
    elif aq_sec <= 5400:
        aq_status = f"FRESH ({aq_str})"
    else:
        aq_status = f"STALE ({aq_str})"

    # Traffic: UTC timestamp, 90 min freshness threshold (hourly batch cadence)
    trf_str, trf_sec = format_time_ago(trf_res["last_ts"], is_utc=True)
    if trf_res["c"] == 0 or trf_sec is None:
        trf_status = "NO DATA"
    elif trf_sec <= 5400:
        trf_status = f"FRESH (Hourly Batch, {trf_str})"
    else:
        trf_status = f"STALE (Batch paused, {trf_str})"

    # IoT: UTC timestamp, 5 min streaming / 60 min standby threshold
    iot_str, iot_sec = format_time_ago(iot_res["last_ts"], is_utc=True)
    if iot_res["c"] == 0 or iot_sec is None:
        iot_status = "STANDBY (Demo Ready)"
    elif iot_sec <= 300:
        iot_status = f"FRESH (Streaming, {iot_str})"
    elif iot_sec <= 3600:
        iot_status = f"STANDBY (Packet {iot_str})"
    else:
        iot_status = f"STANDBY (Offline, {iot_str})"

    return [
        {
            "Source": "Open-Meteo Weather API",
            "Type": "REAL_API",
            "Records": w_res["c"],
            "Last Update": f"{w_res['last_ts']} ({w_str})" if w_res["last_ts"] else "Never",
            "Status": w_status,
        },
        {
            "Source": "Open-Meteo Air Quality API",
            "Type": "REAL_API",
            "Records": aq_res["c"],
            "Last Update": f"{aq_res['last_ts']} ({aq_str})" if aq_res["last_ts"] else "Never",
            "Status": aq_status,
        },
        {
            "Source": "TomTom Traffic Flow API",
            "Type": "REAL_API",
            "Records": trf_res["c"],
            "Last Update": f"{trf_res['last_ts']} ({trf_str})" if trf_res["last_ts"] else "Never",
            "Status": trf_status,
        },
        {
            "Source": "Arduino Uno R3 / IoT Gateway",
            "Type": "REAL_HARDWARE",
            "Records": iot_res["c"],
            "Last Update": f"{iot_res['last_ts']} ({iot_str})" if iot_res["last_ts"] else "Never",
            "Status": iot_status,
        },
    ]
