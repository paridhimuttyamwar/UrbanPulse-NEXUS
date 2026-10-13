"""
UrbanPulse Configuration Module.
Loads environment variables and supplies centralized project settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base Directory: root of urbanpulse project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
load_dotenv(BASE_DIR / ".env")


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

    # Explicit Environment Selection: 'local' (default) vs 'cloud'
    URBANPULSE_ENV: str = os.getenv("URBANPULSE_ENV", "local").lower().strip()

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
    TIDB_HOST: str = os.getenv("TIDB_HOST", "")
    TIDB_PORT: int = int(os.getenv("TIDB_PORT", 4000))
    TIDB_USER: str = os.getenv("TIDB_USER", "")
    TIDB_PASSWORD: str = os.getenv("TIDB_PASSWORD", "")
    TIDB_DATABASE: str = os.getenv("TIDB_DATABASE", "urbanpulse")

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

