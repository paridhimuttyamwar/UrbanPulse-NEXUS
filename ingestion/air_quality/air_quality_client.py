"""
UrbanPulse Air Quality Ingestion Client.
Fetches real-time atmospheric pollutant readings from Open-Meteo Air Quality API.
Preserves raw observations, categorizes AQI according to EPA scales,
and persists validated data idempotently into MySQL.
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


def categorize_us_aqi(aqi: Optional[int]) -> Optional[str]:
    """EPA Standard AQI Category mapping."""
    if aqi is None:
        return None
    if aqi <= 50:
        return "Good"
    elif aqi <= 100:
        return "Moderate"
    elif aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    elif aqi <= 200:
        return "Unhealthy"
    elif aqi <= 300:
        return "Very Unhealthy"
    else:
        return "Hazardous"


class AirQualityIngestionClient:
    def __init__(self):
        self.base_url = settings.OPEN_METEO_AQ_BASE_URL
        self.timeout = settings.API_TIMEOUT_SECONDS
        self.max_retries = settings.API_MAX_RETRIES

    def _generate_event_id(self, location_id: str, timestamp_str: str) -> str:
        """Deterministic unique event ID."""
        hash_input = f"AIR_QUALITY_{location_id}_{timestamp_str}"
        digest = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:16]
        return f"EVT_AQ_{digest.upper()}"

    def fetch_air_quality_for_location(
        self, location_id: str, latitude: float, longitude: float
    ) -> Optional[Dict[str, Any]]:
        """
        Calls Open-Meteo Air Quality API with retries and exponential backoff.
        """
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,ozone,us_aqi,european_aqi",
            "timezone": "auto",
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.get(self.base_url, params=params, timeout=self.timeout)
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(
                        f"AQ API HTTP {response.status_code} for {location_id} (Attempt {attempt}/{self.max_retries}): {response.text}"
                    )
            except requests.RequestException as e:
                logger.warning(
                    f"AQ API error for {location_id} (Attempt {attempt}/{self.max_retries}): {e}"
                )

            if attempt < self.max_retries:
                time.sleep(1.5 * attempt)

        logger.error(f"AQ API failed for {location_id} after {self.max_retries} attempts.")
        return None

    def process_and_store(
        self, location_id: str, latitude: float, longitude: float
    ) -> bool:
        """
        Fetches, validates, archives, and persists air quality records.
        """
        raw_response = self.fetch_air_quality_for_location(location_id, latitude, longitude)
        if not raw_response or "current" not in raw_response:
            err_msg = "Invalid or empty API response from air quality service"
            archiver.archive_rejected(
                event_id=None,
                source="air_quality_api",
                source_type="REAL_API",
                raw_payload=raw_response or {},
                rejection_reason=err_msg,
            )
            repository.insert_rejected_record(
                source_name="air_quality_api",
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
            source="air_quality_api",
            payload=raw_response,
            source_type="REAL_API",
        )

        us_aqi = current.get("us_aqi")
        aqi_category = categorize_us_aqi(us_aqi)

        record_dict = {
            "event_id": event_id,
            "location_id": location_id,
            "timestamp": timestamp_str,
            "pm2_5": current.get("pm2_5"),
            "pm10": current.get("pm10"),
            "nitrogen_dioxide": current.get("nitrogen_dioxide"),
            "ozone": current.get("ozone"),
            "carbon_monoxide": current.get("carbon_monoxide"),
            "us_aqi": us_aqi,
            "european_aqi": current.get("european_aqi"),
            "aqi_category": aqi_category,
            "source_type": "REAL_API",
            "measurement_type": "OBSERVED_OR_MODELED_API",
        }

        # Validation
        validated_record, error_reason = ValidationEngine.validate_air_quality(record_dict)
        if not validated_record:
            repository.insert_rejected_record(
                source_name="air_quality_api",
                source_type="REAL_API",
                raw_payload=record_dict,
                rejection_reason=error_reason or "Validation failed",
                event_id=event_id,
            )
            return False

        # Idempotent DB Write
        repository.insert_air_quality_reading(validated_record)
        archiver.archive_processed(
            event_id=event_id,
            source="air_quality_api",
            record_data=validated_record.model_dump(),
        )

        # Anomaly Detection Integration (safe, non-blocking)
        try:
            from anomaly_detection.rule_engine import anomaly_engine
            anomaly_engine.check_air_quality_reading(record_dict)
        except Exception as anom_err:
            logger.warning(f"Air quality anomaly evaluation deferred: {anom_err}")

        return True

    def ingest_primary_city(self) -> bool:
        """Ingests air quality data specifically for the primary configured city (Nagpur)."""
        return self.process_and_store(
            location_id=settings.DEFAULT_LOCATION_ID,
            latitude=settings.DEFAULT_LATITUDE,
            longitude=settings.DEFAULT_LONGITUDE,
        )

    def ingest_all_locations(self) -> int:
        """Ingests air quality data for all registered database locations."""
        locations = repository.get_all_locations()
        success_count = 0
        for loc in locations:
            loc_id = loc["location_id"]
            lat = float(loc["latitude"])
            lon = float(loc["longitude"])
            if self.process_and_store(loc_id, lat, lon):
                success_count += 1
        return success_count


air_quality_client = AirQualityIngestionClient()
