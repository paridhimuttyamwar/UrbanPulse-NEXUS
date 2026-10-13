"""
UrbanPulse Environmental Analytics Module.
Uses Pandas to compute daily weather and air quality aggregations,
and persists rollups into MySQL daily_environment_metrics.
"""

import logging
from datetime import datetime
import pandas as pd

from database.connection import get_db_cursor

logger = logging.getLogger(__name__)


class EnvironmentAnalytics:
    @staticmethod
    def load_weather_dataframe(limit: int = 10000) -> pd.DataFrame:
        """Loads historical weather readings from MySQL."""
        query = """
        SELECT event_id, location_id, timestamp, temperature_c, relative_humidity_pct,
               wind_speed_kmh, precipitation_mm, weather_condition, source_type
        FROM weather_readings
        ORDER BY timestamp DESC
        LIMIT %(limit)s;
        """
        with get_db_cursor(commit=False) as cursor:
            cursor.execute(query, {"limit": limit})
            rows = cursor.fetchall()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        for col in ["temperature_c", "relative_humidity_pct", "wind_speed_kmh", "precipitation_mm"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    @staticmethod
    def load_air_quality_dataframe(limit: int = 10000) -> pd.DataFrame:
        """Loads historical air quality readings from MySQL."""
        query = """
        SELECT event_id, location_id, timestamp, pm2_5, pm10, nitrogen_dioxide,
               ozone, carbon_monoxide, us_aqi, european_aqi, aqi_category, source_type
        FROM air_quality_readings
        ORDER BY timestamp DESC
        LIMIT %(limit)s;
        """
        with get_db_cursor(commit=False) as cursor:
            cursor.execute(query, {"limit": limit})
            rows = cursor.fetchall()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        for col in ["pm2_5", "pm10", "nitrogen_dioxide", "ozone", "carbon_monoxide", "us_aqi", "european_aqi"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    @classmethod
    def compute_and_store_daily_metrics(cls) -> int:
        """
        Merges weather and air quality readings into daily aggregates per location,
        persisting idempotently into daily_environment_metrics.
        """
        df_weather = cls.load_weather_dataframe(limit=10000)
        df_aq = cls.load_air_quality_dataframe(limit=10000)

        if df_weather.empty and df_aq.empty:
            logger.info("No environmental data to aggregate.")
            return 0

        # Process weather daily metrics
        w_grouped = pd.DataFrame()
        if not df_weather.empty:
            df_weather["date_bucket"] = df_weather["timestamp"].dt.date
            w_grouped = df_weather.groupby(["location_id", "date_bucket"]).agg(
                avg_temperature_c=("temperature_c", "mean"),
                min_temperature_c=("temperature_c", "min"),
                max_temperature_c=("temperature_c", "max"),
                avg_humidity_pct=("relative_humidity_pct", "mean"),
                total_precipitation_mm=("precipitation_mm", "sum"),
            ).reset_index()

        # Process air quality daily metrics
        aq_grouped = pd.DataFrame()
        if not df_aq.empty:
            df_aq["date_bucket"] = df_aq["timestamp"].dt.date
            aq_grouped = df_aq.groupby(["location_id", "date_bucket"]).agg(
                avg_pm2_5=("pm2_5", "mean"),
                avg_pm10=("pm10", "mean"),
                max_aqi=("us_aqi", "max"),
            ).reset_index()

        # Merge weather and air quality metrics
        if not w_grouped.empty and not aq_grouped.empty:
            merged = pd.merge(w_grouped, aq_grouped, on=["location_id", "date_bucket"], how="outer")
        elif not w_grouped.empty:
            merged = w_grouped
            merged["avg_pm2_5"] = None
            merged["avg_pm10"] = None
            merged["max_aqi"] = None
        else:
            merged = aq_grouped
            merged["avg_temperature_c"] = None
            merged["min_temperature_c"] = None
            merged["max_temperature_c"] = None
            merged["avg_humidity_pct"] = None
            merged["total_precipitation_mm"] = None

        insert_query = """
        INSERT INTO daily_environment_metrics (
            location_id, date_bucket, avg_temperature_c, min_temperature_c,
            max_temperature_c, avg_humidity_pct, total_precipitation_mm,
            avg_pm2_5, avg_pm10, max_aqi
        ) VALUES (
            %(location_id)s, %(date_bucket)s, %(avg_temperature_c)s, %(min_temperature_c)s,
            %(max_temperature_c)s, %(avg_humidity_pct)s, %(total_precipitation_mm)s,
            %(avg_pm2_5)s, %(avg_pm10)s, %(max_aqi)s
        )
        ON DUPLICATE KEY UPDATE
            avg_temperature_c = VALUES(avg_temperature_c),
            min_temperature_c = VALUES(min_temperature_c),
            max_temperature_c = VALUES(max_temperature_c),
            avg_humidity_pct = VALUES(avg_humidity_pct),
            total_precipitation_mm = VALUES(total_precipitation_mm),
            avg_pm2_5 = VALUES(avg_pm2_5),
            avg_pm10 = VALUES(avg_pm10),
            max_aqi = VALUES(max_aqi);
        """

        records = merged.to_dict(orient="records")
        with get_db_cursor(commit=True) as cursor:
            for row in records:
                # Sanitize NaN to None for MySQL NULL
                sanitized_row = {
                    k: (None if pd.isna(v) else v) for k, v in row.items()
                }
                cursor.execute(insert_query, sanitized_row)

        logger.info(f"Updated {len(records)} daily environment aggregate metrics.")
        return len(records)


environment_analytics = EnvironmentAnalytics()
