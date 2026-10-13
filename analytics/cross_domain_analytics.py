"""
UrbanPulse Cross-Domain Analytics Module.
Joins and correlates traffic metrics (SIMULATED) with real environmental observations (REAL_API).
Includes statistical correlation analysis and prominent methodology caveats.
"""

import logging
from datetime import date, datetime, time
from typing import Dict, Any, Tuple, Optional
import pandas as pd
from database.connection import get_db_cursor
from analytics.traffic_analytics import traffic_analytics

logger = logging.getLogger(__name__)


def _normalize_date_boundaries(
    start_date: Optional[Any], end_date: Optional[Any]
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Converts date, datetime or string objects into inclusive datetime bounds (00:00:00 to 23:59:59)."""
    start_dt = None
    end_dt = None
    if start_date:
        if isinstance(start_date, datetime):
            start_dt = start_date
        elif isinstance(start_date, date):
            start_dt = datetime.combine(start_date, time.min)
        else:
            try:
                start_dt = pd.to_datetime(start_date).to_pydatetime()
            except Exception:
                pass
    if end_date:
        if isinstance(end_date, datetime):
            end_dt = end_date
        elif isinstance(end_date, date):
            end_dt = datetime.combine(end_date, time.max)
        else:
            try:
                end_dt = pd.to_datetime(end_date).to_pydatetime()
            except Exception:
                pass
    return start_dt, end_dt


class CrossDomainAnalytics:
    CAVEAT_DISCLAIMER: str = (
        "METHODOLOGICAL NOTE: Telemetry derived exclusively from genuine observations (REAL_API). "
        "Statistical associations or correlation coefficients do NOT imply physical causation."
    )
    TRAFFIC_ONLY_DISCLAIMER: str = (
        "METHODOLOGICAL NOTE: Traffic-only correlation matrix shown. Cross-domain correlation requires "
        "sufficient temporally overlapping observations between physical meteorological models and traffic "
        "corridors. Currently insufficient cross-domain paired observations exist for the selected filter."
    )

    @staticmethod
    def is_cross_domain_matrix(corr_df: pd.DataFrame) -> bool:
        """Checks if the correlation matrix includes environmental metrics in addition to mobility."""
        env_metrics = {"temperature_c", "relative_humidity_pct", "wind_speed_kmh", "pm2_5", "pm10", "us_aqi"}
        return any(c in env_metrics for c in corr_df.columns)

    @classmethod
    def load_joined_urban_dataset(
        cls,
        location_id: Optional[str] = None,
        start_date: Optional[Any] = None,
        end_date: Optional[Any] = None,
        source_type: Optional[str] = "REAL_API",
        limit: int = 2000,
    ) -> pd.DataFrame:
        """
        Extracts and aligns traffic, weather, and air quality on city/location
        and rounded hourly timestamps. Reconciles UTC traffic simulation with IST environmental
        observations without repeating single latest values across disparate timestamps.
        """
        where_clauses = ["1=1"]
        params: Dict[str, Any] = {"limit": limit}

        if source_type and source_type != "ALL":
            where_clauses.append("t.source_type = %(source_type)s")
            params["source_type"] = source_type

        if location_id and location_id != "ALL":
            where_clauses.append("r.location_id = %(loc)s")
            params["loc"] = location_id

        start_dt, end_dt = _normalize_date_boundaries(start_date, end_date)
        if start_dt:
            where_clauses.append("TIMESTAMPADD(MINUTE, 330, t.timestamp) >= %(start_dt)s")
            params["start_dt"] = start_dt
        if end_dt:
            where_clauses.append("TIMESTAMPADD(MINUTE, 330, t.timestamp) <= %(end_dt)s")
            params["end_dt"] = end_dt

        where_sql = " AND ".join(where_clauses)

        query = f"""
        SELECT 
            t.timestamp AS traffic_time_utc,
            TIMESTAMPADD(MINUTE, 330, t.timestamp) AS traffic_time,
            r.location_id,
            r.road_name,
            l.city_name,
            t.vehicle_count,
            t.avg_speed_kmh,
            t.congestion_level,
            t.traffic_density_vpk,
            w.temperature_c,
            w.relative_humidity_pct,
            w.wind_speed_kmh,
            w.weather_condition,
            a.pm2_5,
            a.pm10,
            a.us_aqi,
            a.aqi_category
        FROM traffic_readings t
        JOIN road_segments r ON t.segment_id = r.segment_id
        JOIN locations l ON r.location_id = l.location_id
        JOIN (
            -- Group weather by location and hourly timestamp (in IST)
            SELECT 
                location_id,
                DATE_FORMAT(timestamp, '%%Y-%%m-%%d %%H:00:00') AS hour_bucket,
                AVG(temperature_c) AS temperature_c,
                AVG(relative_humidity_pct) AS relative_humidity_pct,
                AVG(wind_speed_kmh) AS wind_speed_kmh,
                MAX(weather_condition) AS weather_condition
            FROM weather_readings
            GROUP BY location_id, DATE_FORMAT(timestamp, '%%Y-%%m-%%d %%H:00:00')
        ) w ON r.location_id = w.location_id 
           AND DATE_FORMAT(TIMESTAMPADD(MINUTE, 330, t.timestamp), '%%Y-%%m-%%d %%H:00:00') = w.hour_bucket
        JOIN (
            -- Group air quality by location and hourly timestamp (in IST)
            SELECT 
                location_id,
                DATE_FORMAT(timestamp, '%%Y-%%m-%%d %%H:00:00') AS hour_bucket,
                AVG(pm2_5) AS pm2_5,
                AVG(pm10) AS pm10,
                AVG(us_aqi) AS us_aqi,
                MAX(aqi_category) AS aqi_category
            FROM air_quality_readings
            GROUP BY location_id, DATE_FORMAT(timestamp, '%%Y-%%m-%%d %%H:00:00')
        ) a ON r.location_id = a.location_id 
           AND DATE_FORMAT(TIMESTAMPADD(MINUTE, 330, t.timestamp), '%%Y-%%m-%%d %%H:00:00') = a.hour_bucket
        WHERE {where_sql}
        ORDER BY t.timestamp DESC
        LIMIT %(limit)s;
        """

        with get_db_cursor(commit=False) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        for col in [
            "vehicle_count", "avg_speed_kmh", "traffic_density_vpk",
            "temperature_c", "relative_humidity_pct", "wind_speed_kmh",
            "pm2_5", "pm10", "us_aqi"
        ]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    @classmethod
    def calculate_correlation_matrix(
        cls,
        location_id: Optional[str] = None,
        start_date: Optional[Any] = None,
        end_date: Optional[Any] = None,
        source_type: Optional[str] = "REAL_API",
    ) -> Tuple[pd.DataFrame, str]:
        """
        Calculates Pearson correlation matrix.
        If valid temporally-aligned cross-domain pairs with non-zero variance exist,
        computes the cross-domain correlation.
        If overlap is insufficient or variance is zero, falls back to a valid traffic-only
        correlation matrix with an explicit methodological note. Never replaces NaN with zeros.
        """
        df = cls.load_joined_urban_dataset(
            location_id=location_id,
            start_date=start_date,
            end_date=end_date,
            source_type=source_type,
        )
        
        # Check if valid cross-domain paired observations exist
        has_cross_domain = False
        if not df.empty and len(df) >= 5:
            # Check for non-zero variance in key environmental fields
            env_cols = [c for c in ["temperature_c", "pm2_5", "us_aqi"] if c in df.columns]
            has_env_variance = any(df[c].dropna().nunique() > 1 and df[c].dropna().var() > 0 for c in env_cols)
            trf_cols = [c for c in ["avg_speed_kmh"] if c in df.columns]
            has_trf_variance = any(df[c].dropna().nunique() > 1 and df[c].dropna().var() > 0 for c in trf_cols)
            if has_env_variance and has_trf_variance:
                has_cross_domain = True

        if has_cross_domain:
            candidate_cols = [
                "avg_speed_kmh",
                "temperature_c", "relative_humidity_pct", "wind_speed_kmh",
                "pm2_5", "us_aqi"
            ]
            # Include only columns with actual variance to avoid NaN
            valid_cols = [
                c for c in candidate_cols 
                if c in df.columns and df[c].dropna().nunique() > 1 and df[c].dropna().var() > 0
            ]
            if len(valid_cols) >= 2:
                corr_matrix = df[valid_cols].corr()
                return corr_matrix, cls.CAVEAT_DISCLAIMER

        # Fallback: Traffic-Only Correlation Matrix
        df_trf = traffic_analytics.load_traffic_dataframe(
            limit=5000,
            location_id=location_id,
            start_date=start_date,
            end_date=end_date,
            source_type=source_type,
        )
        if not df_trf.empty:
            trf_cols = ["avg_speed_kmh", "free_flow_speed_kmh", "current_travel_time_sec", "free_flow_travel_time_sec"]
            valid_trf_cols = [
                c for c in trf_cols 
                if c in df_trf.columns and df_trf[c].dropna().nunique() > 1 and df_trf[c].dropna().var() > 0
            ]
            if len(valid_trf_cols) >= 2:
                trf_corr = df_trf[valid_trf_cols].corr()
                return trf_corr, cls.TRAFFIC_ONLY_DISCLAIMER

        return pd.DataFrame(), cls.TRAFFIC_ONLY_DISCLAIMER


cross_domain_analytics = CrossDomainAnalytics()
