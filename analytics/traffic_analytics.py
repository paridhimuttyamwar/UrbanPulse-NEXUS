"""
UrbanPulse Traffic Analytics Module.
Uses Pandas to compute hourly rollups, speed profiles, peak hours,
and persists aggregates into MySQL hourly_traffic_metrics.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
import pandas as pd

from database.connection import get_db_cursor

logger = logging.getLogger(__name__)


class TrafficAnalytics:
    @staticmethod
    def load_traffic_dataframe(
        limit: int = 10000,
        location_id: Optional[str] = None,
        start_date: Optional[Any] = None,
        end_date: Optional[Any] = None,
        source_type: Optional[str] = "REAL_API",
    ) -> pd.DataFrame:
        """Loads historical traffic readings from MySQL into a Pandas DataFrame, optionally filtered by location, date range, and source_type."""
        from datetime import date, time
        query = """
        SELECT t.event_id, t.sensor_id, t.segment_id, t.timestamp, t.vehicle_count,
               t.avg_speed_kmh, t.free_flow_speed_kmh, t.current_travel_time_sec,
               t.free_flow_travel_time_sec, t.confidence_score, t.road_closure,
               t.congestion_level, t.traffic_density_vpk, t.source_type,
               r.road_name
        FROM traffic_readings t
        JOIN road_segments r ON t.segment_id = r.segment_id
        WHERE 1=1
        """
        params: Dict[str, Any] = {"limit": limit}
        if source_type and source_type != "ALL":
            query += " AND t.source_type = %(source_type)s"
            params["source_type"] = source_type
        if location_id and location_id != "ALL":
            query += " AND r.location_id = %(loc)s"
            params["loc"] = location_id

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

        query += " ORDER BY t.timestamp DESC LIMIT %(limit)s;"

        with get_db_cursor(commit=False) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        numeric_cols = [
            "vehicle_count",
            "avg_speed_kmh",
            "free_flow_speed_kmh",
            "current_travel_time_sec",
            "free_flow_travel_time_sec",
            "confidence_score",
            "traffic_density_vpk",
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    @classmethod
    def compute_and_store_hourly_metrics(cls) -> int:
        """
        Aggregates traffic data into hourly buckets and writes idempotently
        into hourly_traffic_metrics table.
        """
        df = cls.load_traffic_dataframe(limit=50000)
        if df.empty:
            logger.info("No traffic readings found to aggregate.")
            return 0

        # Floor timestamps to hour
        df["hour_bucket"] = df["timestamp"].dt.floor("h")

        # Map congestion to numeric index (LOW=1, MEDIUM=2, HIGH=3, SEVERE=4)
        congestion_map = {"LOW": 1.0, "MEDIUM": 2.0, "HIGH": 3.0, "SEVERE": 4.0}
        df["congestion_score"] = df["congestion_level"].map(congestion_map).fillna(1.0)

        # Aggregate by segment and hour
        grouped = df.groupby(["segment_id", "hour_bucket"]).agg(
            avg_vehicle_count=("vehicle_count", "mean"),
            avg_speed_kmh=("avg_speed_kmh", "mean"),
            peak_vehicle_count=("vehicle_count", "max"),
            congestion_index=("congestion_score", "mean"),
            sample_count=("event_id", "count"),
        ).reset_index()

        insert_query = """
        INSERT INTO hourly_traffic_metrics (
            segment_id, hour_bucket, avg_vehicle_count, avg_speed_kmh,
            peak_vehicle_count, congestion_index, sample_count
        ) VALUES (
            %(segment_id)s, %(hour_bucket)s, %(avg_vehicle_count)s, %(avg_speed_kmh)s,
            %(peak_vehicle_count)s, %(congestion_index)s, %(sample_count)s
        )
        ON DUPLICATE KEY UPDATE
            avg_vehicle_count = VALUES(avg_vehicle_count),
            avg_speed_kmh = VALUES(avg_speed_kmh),
            peak_vehicle_count = VALUES(peak_vehicle_count),
            congestion_index = VALUES(congestion_index),
            sample_count = VALUES(sample_count);
        """

        records = grouped.to_dict(orient="records")
        with get_db_cursor(commit=True) as cursor:
            for row in records:
                row["hour_bucket"] = row["hour_bucket"].to_pydatetime()
                cursor.execute(insert_query, row)

        logger.info(f"Updated {len(records)} hourly traffic aggregate metrics.")
        return len(records)

    @classmethod
    def get_peak_hours_summary(
        cls,
        location_id: Optional[str] = None,
        source_type: Optional[str] = "REAL_API",
    ) -> pd.DataFrame:
        """Calculates citywide average traffic metrics grouped by hour of the day, filtered by location and source_type."""
        df = cls.load_traffic_dataframe(limit=10000, location_id=location_id, source_type=source_type)
        if df.empty:
            return pd.DataFrame()

        df["hour_of_day"] = df["timestamp"].dt.hour
        summary = df.groupby("hour_of_day").agg(
            mean_volume=("vehicle_count", "mean"),
            mean_speed=("avg_speed_kmh", "mean"),
            observations=("event_id", "count"),
        ).reset_index().sort_values("hour_of_day")

        return summary


traffic_analytics = TrafficAnalytics()
