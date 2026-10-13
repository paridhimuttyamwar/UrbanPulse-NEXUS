"""
UrbanPulse Validation Engine.
Validates inbound payloads, handles rejection tracking, and ensures data hygiene.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, Type
from pydantic import BaseModel, ValidationError

from validation.models import (
    WeatherRecord,
    AirQualityRecord,
    TrafficRecord,
    IoTSensorRecord,
)
from storage.raw_archiver import archiver

logger = logging.getLogger(__name__)


class ValidationEngine:
    @staticmethod
    def validate_record(
        model_cls: Type[BaseModel],
        payload: Dict[str, Any],
        source_name: str,
        source_type: str,
    ) -> Tuple[Optional[BaseModel], Optional[str]]:
        """
        Validates a payload dictionary against a Pydantic model.
        Returns: (validated_model_instance, None) on success.
                 (None, error_reason) on failure, and logs to rejected storage.
        """
        try:
            instance = model_cls.model_validate(payload)
            return instance, None
        except ValidationError as e:
            error_msgs = []
            for err in e.errors():
                loc = ".".join(str(l) for l in err.get("loc", []))
                msg = err.get("msg", "invalid")
                error_msgs.append(f"Field '{loc}': {msg}")
            error_summary = "; ".join(error_msgs)
            
            event_id = payload.get("event_id") if isinstance(payload, dict) else None
            
            # Archive rejected record to disk
            archiver.archive_rejected(
                event_id=event_id,
                source=source_name,
                source_type=source_type,
                raw_payload=payload,
                rejection_reason=error_summary,
            )
            
            logger.warning(
                f"Validation failed for {source_name} [{event_id}]: {error_summary}"
            )
            return None, error_summary
        except Exception as ex:
            error_summary = f"Unexpected validation error: {str(ex)}"
            event_id = payload.get("event_id") if isinstance(payload, dict) else None
            
            archiver.archive_rejected(
                event_id=event_id,
                source=source_name,
                source_type=source_type,
                raw_payload=payload,
                rejection_reason=error_summary,
            )
            logger.error(f"Unexpected error in validator: {ex}")
            return None, error_summary

    @classmethod
    def validate_weather(
        cls, payload: Dict[str, Any]
    ) -> Tuple[Optional[WeatherRecord], Optional[str]]:
        return cls.validate_record(WeatherRecord, payload, "weather_api", "REAL_API")

    @classmethod
    def validate_air_quality(
        cls, payload: Dict[str, Any]
    ) -> Tuple[Optional[AirQualityRecord], Optional[str]]:
        return cls.validate_record(AirQualityRecord, payload, "air_quality_api", "REAL_API")

    @classmethod
    def validate_traffic(
        cls,
        payload: Dict[str, Any],
        source_name: str = "traffic_simulator",
        source_type: str = "SIMULATED",
    ) -> Tuple[Optional[TrafficRecord], Optional[str]]:
        src_type = payload.get("source_type", source_type) if isinstance(payload, dict) else source_type
        return cls.validate_record(TrafficRecord, payload, source_name, src_type)

    @classmethod
    def validate_iot(
        cls, payload: Dict[str, Any]
    ) -> Tuple[Optional[IoTSensorRecord], Optional[str]]:
        return cls.validate_record(IoTSensorRecord, payload, "arduino_gateway", "REAL_HARDWARE")
