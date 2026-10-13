"""
UrbanPulse Configuration Module.
Loads environment variables and supplies centralized project settings.
"""

import os
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

# Base Directory: root of urbanpulse project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
load_dotenv(BASE_DIR / ".env")


def _get_config_value(key: str, default: Any = "") -> Any:
    """
    Retrieves configuration value, prioritizing os.environ, then falling back to st.secrets.
    Safe when Streamlit is not installed or when st.secrets is unavailable.
    """
    val = os.getenv(key)
    if val is not None and str(val).strip() != "":
        return val

    # Fallback to Streamlit secrets if available
    try:
        import streamlit as st
        if hasattr(st, "secrets") and st.secrets is not None:
            # 1. Direct match (e.g. TIDB_HOST)
            if key in st.secrets:
                sec_val = st.secrets[key]
                if sec_val is not None and str(sec_val).strip() != "":
                    return sec_val
            # 2. Lowercase match (e.g. tidb_host)
            key_lower = key.lower()
            if key_lower in st.secrets:
                sec_val = st.secrets[key_lower]
                if sec_val is not None and str(sec_val).strip() != "":
                    return sec_val
            # 3. Nested [tidb] section match (e.g. [tidb] host = "...")
            if key.startswith("TIDB_") and "tidb" in st.secrets:
                tidb_sec = st.secrets["tidb"]
                sub_key = key[5:].lower()
                if sub_key in tidb_sec:
                    sec_val = tidb_sec[sub_key]
                    if sec_val is not None and str(sec_val).strip() != "":
                        return sec_val
    except Exception:
        pass

    return default


class Settings:
    # Project Info
    PROJECT_NAME: str = "UrbanPulse"
    VERSION: str = "1.0.0"
    BASE_DIR: Path = BASE_DIR

    # Primary / Default City Configuration (Nagpur)
    DEFAULT_CITY_NAME: str = "Nagpur"
    DEFAULT_STATE_NAME: str = "Maharashtra"
    DEFAULT_COUNTRY: str = "India"
    DEFAULT_LOCATION_ID: str = "LOC_NAGPUR"
    DEFAULT_LATITUDE: float = 21.1458
    DEFAULT_LONGITUDE: float = 79.0882
    DEFAULT_TIMEZONE: str = "Asia/Kolkata"

    def __init__(self):
        self._urbanpulse_env = None
        self._tidb_host = None
        self._tidb_port = None
        self._tidb_user = None
        self._tidb_password = None
        self._tidb_database = None

    # Explicit Environment Selection: 'local' (default) vs 'cloud'
    @property
    def URBANPULSE_ENV(self) -> str:
        if self._urbanpulse_env is not None:
            return self._urbanpulse_env.lower().strip()
        return str(_get_config_value("URBANPULSE_ENV", "local")).lower().strip()

    @URBANPULSE_ENV.setter
    def URBANPULSE_ENV(self, val: str):
        self._urbanpulse_env = val

    @property
    def is_cloud(self) -> bool:
        return self.URBANPULSE_ENV == "cloud"

    @property
    def is_local(self) -> bool:
        return self.URBANPULSE_ENV != "cloud"

    # MySQL Configuration (Local Development)
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", 3306))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "root123")
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "urbanpulse")

    # TiDB Cloud Configuration (Secure Cloud Operations)
    @property
    def TIDB_HOST(self) -> str:
        if self._tidb_host is not None:
            return self._tidb_host
        return str(_get_config_value("TIDB_HOST", ""))

    @TIDB_HOST.setter
    def TIDB_HOST(self, val: str):
        self._tidb_host = val

    @property
    def TIDB_PORT(self) -> int:
        if self._tidb_port is not None:
            return int(self._tidb_port)
        return int(_get_config_value("TIDB_PORT", 4000))

    @TIDB_PORT.setter
    def TIDB_PORT(self, val: Any):
        self._tidb_port = val

    @property
    def TIDB_USER(self) -> str:
        if self._tidb_user is not None:
            return self._tidb_user
        return str(_get_config_value("TIDB_USER", ""))

    @TIDB_USER.setter
    def TIDB_USER(self, val: str):
        self._tidb_user = val

    @property
    def TIDB_PASSWORD(self) -> str:
        if self._tidb_password is not None:
            return self._tidb_password
        return str(_get_config_value("TIDB_PASSWORD", ""))

    @TIDB_PASSWORD.setter
    def TIDB_PASSWORD(self, val: str):
        self._tidb_password = val

    @property
    def TIDB_DATABASE(self) -> str:
        if self._tidb_database is not None:
            return self._tidb_database
        return str(_get_config_value("TIDB_DATABASE", "urbanpulse"))

    @TIDB_DATABASE.setter
    def TIDB_DATABASE(self, val: str):
        self._tidb_database = val

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    KAFKA_TRAFFIC_TOPIC: str = os.getenv("KAFKA_TRAFFIC_TOPIC", "urbanpulse.traffic.raw")
    KAFKA_IOT_TOPIC: str = os.getenv("KAFKA_IOT_TOPIC", "urbanpulse.iot.raw")
    KAFKA_CONSUMER_GROUP: str = os.getenv("KAFKA_CONSUMER_GROUP", "urbanpulse_traffic_consumer_group")

    # Arduino Serial Configuration
    ARDUINO_PORT: str = os.getenv("ARDUINO_PORT", "AUTO")
    ARDUINO_BAUD_RATE: int = int(os.getenv("ARDUINO_BAUD_RATE", 9600))
    GATEWAY_STATE_FILE: Path = BASE_DIR / "data" / "gateway_state.json"

    # Open-Meteo API Configuration
    OPEN_METEO_BASE_URL: str = os.getenv(
        "OPEN_METEO_BASE_URL", "https://api.open-meteo.com/v1/forecast"
    )
    OPEN_METEO_AQ_BASE_URL: str = os.getenv(
        "OPEN_METEO_AQ_BASE_URL", "https://air-quality-api.open-meteo.com/v1/air-quality"
    )
    API_TIMEOUT_SECONDS: int = int(os.getenv("API_TIMEOUT_SECONDS", 10))
    API_MAX_RETRIES: int = int(os.getenv("API_MAX_RETRIES", 3))

    # TomTom API Configuration
    TOMTOM_API_KEY: str = os.getenv("TOMTOM_API_KEY", "")
    TOMTOM_TRAFFIC_FLOW_BASE_URL: str = os.getenv(
        "TOMTOM_TRAFFIC_FLOW_BASE_URL",
        "https://api.tomtom.com/traffic/services/4/flowSegmentData/relative0/10/json",
    )
    TOMTOM_MONTHLY_BUDGET: int = int(os.getenv("TOMTOM_MONTHLY_BUDGET", 16000))
    TOMTOM_SAFETY_MARGIN: int = int(os.getenv("TOMTOM_SAFETY_MARGIN", 500))
    # Documented conservative opening balance for October 2026 (accounts for earlier development & probe attempts)
    TOMTOM_CONSERVATIVE_OPENING_BALANCE: int = int(os.getenv("TOMTOM_CONSERVATIVE_OPENING_BALANCE", 200))
    TOMTOM_USAGE_STATE_FILE: Path = BASE_DIR / "data" / "tomtom_usage_state.json"

    # Traffic Simulator Configuration
    SIMULATOR_FREQUENCY_SECONDS: float = float(os.getenv("SIMULATOR_FREQUENCY_SECONDS", 2.0))
    SIMULATOR_NUM_SEGMENTS: int = int(os.getenv("SIMULATOR_NUM_SEGMENTS", 15))

    # Data Storage Directories
    RAW_DATA_DIR: Path = BASE_DIR / os.getenv("RAW_DATA_DIR", "data/raw")
    PROCESSED_DATA_DIR: Path = BASE_DIR / os.getenv("PROCESSED_DATA_DIR", "data/processed")
    REJECTED_DATA_DIR: Path = BASE_DIR / os.getenv("REJECTED_DATA_DIR", "data/rejected")
    LOGS_DIR: Path = BASE_DIR / "logs"


settings = Settings()
GATEWAY_STATE_FILE = settings.GATEWAY_STATE_FILE

# Ensure directories exist
for directory in [
    settings.RAW_DATA_DIR,
    settings.PROCESSED_DATA_DIR,
    settings.REJECTED_DATA_DIR,
    settings.LOGS_DIR,
]:
    directory.mkdir(parents=True, exist_ok=True)

