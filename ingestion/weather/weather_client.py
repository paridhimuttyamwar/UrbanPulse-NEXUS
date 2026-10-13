"""
UrbanPulse Weather Ingestion Client.
Fetches real-time weather observations from Open-Meteo API with retry policies,
timeout safeguards, raw data archival, and idempotent database loading.
"""

import hashlib
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
import requests

from config.settings import settings
from storage.raw_archiver import archiver
from validation.validator import ValidationEngine
from database.repository import repository

logger = logging.getLogger(__name__)

# WMO Weather interpretation codes (WW) mapping
WMO_WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


class WeatherIngestionClient:
    def __init__(self):
        self.base_url = settings.OPEN_METEO_BASE_URL
        self.timeout = settings.API_TIMEOUT_SECONDS
        self.max_retries = settings.API_MAX_RETRIES

    def _generate_event_id(self, location_id: str, timestamp_str: str) -> str:
        """Generates deterministic unique event ID for duplicate prevention."""
        hash_input = f"WEATHER_{location_id}_{timestamp_str}"
        digest = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:16]
        return f"EVT_WTH_{digest.upper()}"

    def fetch_weather_for_location(
        self, location_id: str, latitude: float, longitude: float
    ) -> Optional[Dict[str, Any]]:
        """
        Calls Open-Meteo forecast API with bounded retries and exponential backoff.
        """
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
            "timezone": "auto",
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.get(self.base_url, params=params, timeout=self.timeout)
                if response.status_code == 200:
                    payload = response.json()
                    return payload
                else:
                    logger.warning(
                        f"Weather API HTTP {response.status_code} for {location_id} (Attempt {attempt}/{self.max_retries}): {response.text}"
                    )
            except requests.RequestException as e:
                logger.warning(
                    f"Weather API network error for {location_id} (Attempt {attempt}/{self.max_retries}): {e}"
                )

            if attempt < self.max_retries:
                time.sleep(1.5 * attempt)

        logger.error(f"Weather API failed for {location_id} after {self.max_retries} attempts.")
        return None

    def process_and_store(
        self, location_id: str, latitude: float, longitude: float
    ) -> bool:
        """
        Fetches, archives raw response, validates, and idempotently inserts weather record.
        """
        raw_response = self.fetch_weather_for_location(location_id, latitude, longitude)
        if not raw_response or "current" not in raw_response:
            err_msg = "Invalid or empty API response from weather service"
            archiver.archive_rejected(
                event_id=None,
                source="weather_api",
                source_type="REAL_API",
                raw_payload=raw_response or {},
                rejection_reason=err_msg,
            )
            repository.insert_rejected_record(
                source_name="weather_api",
                source_type="REAL_API",
                raw_payload=raw_response or {},
                rejection_reason=err_msg,
            )
            return False

        current = raw_response["current"]
        timestamp_str = current.get("time")
        event_id = self._generate_event_id(location_id, timestamp_str)

        # Archive raw response
        archiver.archive_raw(
            event_id=event_id,
            source="weather_api",
            payload=raw_response,
            source_type="REAL_API",
        )

        wmo_code = current.get("weather_code")
        condition_desc = WMO_WEATHER_CODES.get(wmo_code, f"Code {wmo_code}")

        record_dict = {
            "event_id": event_id,
            "location_id": location_id,
            "timestamp": timestamp_str,
            "temperature_c": current.get("temperature_2m"),
            "relative_humidity_pct": current.get("relative_humidity_2m"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "precipitation_mm": current.get("precipitation"),
            "weather_condition": condition_desc,
            "weather_code": wmo_code,
            "source_type": "REAL_API",
            "measurement_type": "OBSERVED_API",
        }

        # Validation
        validated_record, error_reason = ValidationEngine.validate_weather(record_dict)
        if not validated_record:
            repository.insert_rejected_record(
                source_name="weather_api",
                source_type="REAL_API",
                raw_payload=record_dict,
                rejection_reason=error_reason or "Validation failed",
                event_id=event_id,
            )
            return False

        # Idempotent DB Write
        repository.insert_weather_reading(validated_record)
        archiver.archive_processed(
            event_id=event_id,
            source="weather_api",
            record_data=validated_record.model_dump(),
        )

        # Anomaly Detection Integration (safe, non-blocking)
        try:
            from anomaly_detection.rule_engine import anomaly_engine
            anomaly_engine.check_weather_reading(record_dict)
        except Exception as anom_err:
            logger.warning(f"Weather anomaly evaluation deferred: {anom_err}")

        return True

    def ingest_primary_city(self) -> bool:
        """Ingests weather data specifically for the primary configured city (Nagpur)."""
        return self.process_and_store(
            location_id=settings.DEFAULT_LOCATION_ID,
            latitude=settings.DEFAULT_LATITUDE,
            longitude=settings.DEFAULT_LONGITUDE,
        )

    def ingest_all_locations(self) -> int:
        """Ingests weather data for all registered database locations."""
        locations = repository.get_all_locations()
        success_count = 0
        for loc in locations:
            loc_id = loc["location_id"]
            lat = float(loc["latitude"])
            lon = float(loc["longitude"])
            if self.process_and_store(loc_id, lat, lon):
                success_count += 1
        return success_count


weather_client = WeatherIngestionClient()
