"""
UrbanPulse Database Repository.
Provides idempotent insertion and query functions for MySQL.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from database.connection import get_db_cursor
from validation.models import WeatherRecord, AirQualityRecord, TrafficRecord, IoTSensorRecord, IoTDeviceRecord

logger = logging.getLogger(__name__)


class DatabaseRepository:
    @staticmethod
    def get_all_locations() -> List[Dict[str, Any]]:
        """Fetches all registered locations."""
        with get_db_cursor(commit=False) as cursor:
            cursor.execute("SELECT location_id, city_name, state_name, latitude, longitude, timezone FROM locations")
            return cursor.fetchall()

    @staticmethod
    def get_all_road_segments(location_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches registered road segments, optionally filtered by location_id."""
        query = """
            SELECT r.segment_id, r.location_id, r.road_name, r.segment_type, 
                   r.speed_limit_kmh, r.length_km, r.capacity_vph,
                   s.sensor_id, s.sensor_name
            FROM road_segments r
            LEFT JOIN traffic_sensors s ON r.segment_id = s.segment_id
        """
        params = {}
        if location_id and location_id != "ALL":
            query += " WHERE r.location_id = %(loc)s"
            params["loc"] = location_id

        with get_db_cursor(commit=False) as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    @staticmethod
    def insert_weather_reading(record: WeatherRecord) -> bool:
        """Idempotently inserts a weather reading record."""
        query = """
        INSERT INTO weather_readings (
            event_id, location_id, timestamp, temperature_c, relative_humidity_pct,
            wind_speed_kmh, precipitation_mm, weather_condition, weather_code,
            source_type, measurement_type
        ) VALUES (
            %(event_id)s, %(location_id)s, %(timestamp)s, %(temperature_c)s, %(relative_humidity_pct)s,
            %(wind_speed_kmh)s, %(precipitation_mm)s, %(weather_condition)s, %(weather_code)s,
            %(source_type)s, %(measurement_type)s
        )
        ON DUPLICATE KEY UPDATE
            temperature_c = VALUES(temperature_c),
            relative_humidity_pct = VALUES(relative_humidity_pct),
            wind_speed_kmh = VALUES(wind_speed_kmh),
            precipitation_mm = VALUES(precipitation_mm),
            weather_condition = VALUES(weather_condition),
            weather_code = VALUES(weather_code);
        """
        data = record.model_dump()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(query, data)
            return True

    @staticmethod
    def insert_air_quality_reading(record: AirQualityRecord) -> bool:
        """Idempotently inserts an air quality reading record."""
        query = """
        INSERT INTO air_quality_readings (
            event_id, location_id, timestamp, pm2_5, pm10,
            nitrogen_dioxide, ozone, carbon_monoxide, us_aqi,
            european_aqi, aqi_category, source_type, measurement_type
        ) VALUES (
            %(event_id)s, %(location_id)s, %(timestamp)s, %(pm2_5)s, %(pm10)s,
            %(nitrogen_dioxide)s, %(ozone)s, %(carbon_monoxide)s, %(us_aqi)s,
            %(european_aqi)s, %(aqi_category)s, %(source_type)s, %(measurement_type)s
        )
        ON DUPLICATE KEY UPDATE
            pm2_5 = VALUES(pm2_5),
            pm10 = VALUES(pm10),
            nitrogen_dioxide = VALUES(nitrogen_dioxide),
            ozone = VALUES(ozone),
            carbon_monoxide = VALUES(carbon_monoxide),
            us_aqi = VALUES(us_aqi),
            european_aqi = VALUES(european_aqi),
            aqi_category = VALUES(aqi_category);
        """
        data = record.model_dump()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(query, data)
            return True

    @staticmethod
    def insert_traffic_reading(record: TrafficRecord) -> bool:
        """Idempotently inserts a traffic reading record (supporting simulated and live API flow)."""
        query = """
        INSERT INTO traffic_readings (
            event_id, sensor_id, segment_id, timestamp, vehicle_count,
            avg_speed_kmh, free_flow_speed_kmh, current_travel_time_sec,
            free_flow_travel_time_sec, confidence_score, road_closure,
            congestion_level, traffic_density_vpk, source_type
        ) VALUES (
            %(event_id)s, %(sensor_id)s, %(segment_id)s, %(timestamp)s, %(vehicle_count)s,
            %(avg_speed_kmh)s, %(free_flow_speed_kmh)s, %(current_travel_time_sec)s,
            %(free_flow_travel_time_sec)s, %(confidence_score)s, %(road_closure)s,
            %(congestion_level)s, %(traffic_density_vpk)s, %(source_type)s
        )
        ON DUPLICATE KEY UPDATE
            vehicle_count = VALUES(vehicle_count),
            avg_speed_kmh = VALUES(avg_speed_kmh),
            free_flow_speed_kmh = VALUES(free_flow_speed_kmh),
            current_travel_time_sec = VALUES(current_travel_time_sec),
            free_flow_travel_time_sec = VALUES(free_flow_travel_time_sec),
            confidence_score = VALUES(confidence_score),
            road_closure = VALUES(road_closure),
            congestion_level = VALUES(congestion_level),
            traffic_density_vpk = VALUES(traffic_density_vpk);
        """
        data = record.model_dump()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(query, data)
            return True

    @staticmethod
    def insert_iot_reading(record: IoTSensorRecord) -> bool:
        """Idempotently inserts an Arduino IoT sensor reading."""
        query = """
        INSERT INTO iot_sensor_readings (
            event_id, device_id, sensor_type, reading_value,
            unit, timestamp, raw_reading_text, source_type
        ) VALUES (
            %(event_id)s, %(device_id)s, %(sensor_type)s, %(reading_value)s,
            %(unit)s, %(timestamp)s, %(raw_reading_text)s, %(source_type)s
        )
        ON DUPLICATE KEY UPDATE
            reading_value = VALUES(reading_value),
            raw_reading_text = VALUES(raw_reading_text);
        """
        data = record.model_dump()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(query, data)
            return True

    @staticmethod
    def insert_iot_device(record: IoTDeviceRecord) -> bool:
        """Idempotently registers an IoT hardware or virtual device."""
        query = """
        INSERT INTO iot_devices (
            device_id, device_name, device_model, device_type,
            location_id, connected_sensors, port_assignment, status, last_heartbeat
        ) VALUES (
            %(device_id)s, %(device_name)s, %(device_model)s, %(device_type)s,
            %(location_id)s, %(connected_sensors)s, %(port_assignment)s, %(status)s, %(last_heartbeat)s
        )
        ON DUPLICATE KEY UPDATE
            device_name = VALUES(device_name),
            device_model = VALUES(device_model),
            device_type = VALUES(device_type),
            location_id = VALUES(location_id),
            connected_sensors = VALUES(connected_sensors),
            port_assignment = VALUES(port_assignment),
            status = VALUES(status);
        """
        data = record.model_dump()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(query, data)
            return True


    @staticmethod
    def insert_rejected_record(
        source_name: str,
        source_type: str,
        raw_payload: Any,
        rejection_reason: str,
        event_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> bool:
        """Records validation-rejected records into MySQL."""
        query = """
        INSERT INTO rejected_records (
            event_id, source_name, source_type, raw_payload, rejection_reason, timestamp
        ) VALUES (
            %(event_id)s, %(source_name)s, %(source_type)s, %(raw_payload)s, %(rejection_reason)s, %(timestamp)s
        );
        """
        data = {
            "event_id": event_id,
            "source_name": source_name,
            "source_type": source_type,
            "raw_payload": json.dumps(raw_payload, default=str),
            "rejection_reason": rejection_reason,
            "timestamp": timestamp or datetime.utcnow(),
        }
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(query, data)
            return True

    @staticmethod
    def log_pipeline_run(
        run_id: str,
        pipeline_name: str,
        status: str,
        records_processed: int,
        records_rejected: int,
        started_at: datetime,
        finished_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Logs pipeline execution telemetry."""
        query = """
        INSERT INTO pipeline_runs (
            run_id, pipeline_name, status, records_processed, records_rejected,
            started_at, finished_at, error_message
        ) VALUES (
            %(run_id)s, %(pipeline_name)s, %(status)s, %(records_processed)s, %(records_rejected)s,
            %(started_at)s, %(finished_at)s, %(error_message)s
        )
        ON DUPLICATE KEY UPDATE
            status = VALUES(status),
            records_processed = VALUES(records_processed),
            records_rejected = VALUES(records_rejected),
            finished_at = VALUES(finished_at),
            error_message = VALUES(error_message);
        """
        data = {
            "run_id": run_id,
            "pipeline_name": pipeline_name,
            "status": status,
            "records_processed": records_processed,
            "records_rejected": records_rejected,
            "started_at": started_at,
            "finished_at": finished_at,
            "error_message": error_message,
        }
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(query, data)
            return True


repository = DatabaseRepository()
