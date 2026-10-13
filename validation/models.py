"""
UrbanPulse Validation Models.
Defines strongly-typed Pydantic schemas for all domain entities.
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator


class WeatherRecord(BaseModel):
    event_id: str = Field(..., min_length=5, description="Unique weather event ID")
    location_id: str = Field(..., min_length=3, description="FK to locations table")
    timestamp: datetime
    temperature_c: Optional[float] = Field(None, ge=-60.0, le=65.0)
    relative_humidity_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    wind_speed_kmh: Optional[float] = Field(None, ge=0.0, le=300.0)
    precipitation_mm: Optional[float] = Field(None, ge=0.0, le=1000.0)
    weather_condition: Optional[str] = None
    weather_code: Optional[int] = None
    source_type: Literal["REAL_API", "SIMULATED", "REAL_HARDWARE"] = "REAL_API"
    measurement_type: str = "OBSERVED_API"


class AirQualityRecord(BaseModel):
    event_id: str = Field(..., min_length=5, description="Unique AQ event ID")
    location_id: str = Field(..., min_length=3, description="FK to locations table")
    timestamp: datetime
    pm2_5: Optional[float] = Field(None, ge=0.0, le=1000.0)
    pm10: Optional[float] = Field(None, ge=0.0, le=2000.0)
    nitrogen_dioxide: Optional[float] = Field(None, ge=0.0, le=1000.0)
    ozone: Optional[float] = Field(None, ge=0.0, le=1000.0)
    carbon_monoxide: Optional[float] = Field(None, ge=0.0, le=50000.0)
    us_aqi: Optional[int] = Field(None, ge=0, le=500)
    european_aqi: Optional[int] = Field(None, ge=0, le=500)
    aqi_category: Optional[str] = None
    source_type: Literal["REAL_API", "SIMULATED", "REAL_HARDWARE"] = "REAL_API"
    measurement_type: str = "OBSERVED_OR_MODELED_API"


class TrafficRecord(BaseModel):
    event_id: str = Field(..., min_length=5, description="Unique traffic event ID")
    sensor_id: str = Field(..., min_length=3, description="FK to traffic_sensors")
    segment_id: str = Field(..., min_length=3, description="FK to road_segments")
    timestamp: datetime
    vehicle_count: Optional[int] = Field(None, ge=0, le=6000, description="Observed loop detector vehicle count (NULL for live traffic API flow)")
    avg_speed_kmh: float = Field(..., ge=0.0, le=200.0, description="Actual observed harmonic mean speed")
    free_flow_speed_kmh: Optional[float] = Field(None, ge=0.0, le=200.0, description="Expected unconstrained free-flow speed")
    current_travel_time_sec: Optional[int] = Field(None, ge=0, description="Travel time across segment in seconds")
    free_flow_travel_time_sec: Optional[int] = Field(None, ge=0, description="Free flow travel time in seconds")
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Measurement quality confidence from TomTom")
    road_closure: Optional[bool] = Field(False, description="Whether segment is closed to vehicular traffic")
    congestion_level: Literal["LOW", "MEDIUM", "HIGH", "SEVERE"]
    traffic_density_vpk: Optional[float] = Field(None, ge=0.0, le=500.0, description="Vehicles per km (NULL for live traffic API flow)")
    source_type: Literal["SIMULATED", "REAL_API", "REAL_HARDWARE"] = "SIMULATED"


class IoTSensorRecord(BaseModel):
    event_id: str = Field(..., min_length=5, description="Unique IoT event ID")
    device_id: str = Field(..., min_length=3, description="FK to iot_devices")
    sensor_type: str = Field(..., min_length=2, description="e.g. DHT11_TEMP, MQ135_RAW, LDR")
    reading_value: float = Field(..., description="Sensor numerical reading")
    unit: str = Field(..., description="e.g. C, %, RAW_ADC, LUX")
    timestamp: datetime
    raw_reading_text: Optional[str] = None
    source_type: Literal["REAL_HARDWARE", "SIMULATED", "UNVERIFIED_LEGACY"] = "REAL_HARDWARE"


class IoTDeviceRecord(BaseModel):
    device_id: str = Field(..., min_length=3, description="Unique device ID")
    device_name: str = Field(..., min_length=2, description="Descriptive node name")
    device_model: str = Field("Arduino Uno R3", description="Microcontroller board model")
    device_type: Literal["PHYSICAL", "VIRTUAL"] = "PHYSICAL"
    location_id: Optional[str] = "LOC_NAGPUR"
    connected_sensors: Optional[str] = "DHT11,MQ-135,LDR"
    port_assignment: Optional[str] = None
    status: Literal["ONLINE", "OFFLINE", "ERROR"] = "OFFLINE"
    last_heartbeat: Optional[datetime] = None

