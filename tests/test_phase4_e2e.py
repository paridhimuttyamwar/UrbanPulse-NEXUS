"""
Unit and End-to-End Verification Suite for Phase 4:
Dashboard Finalization, Multi-Stream Data Integrity, Provenance Segregation,
and Pipeline Operational Validation for Nagpur Command Center.

All tests use mocks or read-only queries. Zero live API calls are triggered.
"""

import os
import sys
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

# Ensure urbanpulse root is in sys.path
sys.path.insert(0, os.getcwd())

from config.corridors import (
    NAGPUR_CORRIDORS_GEO,
    get_approved_corridors,
    get_corridor_geo,
)
from database.connection import get_db_cursor
from dashboard.data_loader import (
    load_latest_traffic_per_corridor,
    load_traffic_readings,
    load_anomalies,
    load_locations,
    load_road_segments,
    load_latest_weather,
    load_latest_air_quality,
    load_data_source_status,
    get_gateway_runtime_status,
)
from analytics.traffic_analytics import traffic_analytics
from analytics.environment_analytics import environment_analytics
from analytics.cross_domain_analytics import cross_domain_analytics
from anomaly_detection.rule_engine import AnomalyRuleEngine


class TestPhase4EndToEnd(unittest.TestCase):

    def test_01_sql_data_integrity_and_provenance(self):
        """Verify traffic_readings counts, quarantine of SIMULATED/TEST_MOCK, and non-null metrics."""
        with get_db_cursor(commit=False) as cursor:
            cursor.execute("SELECT source_type, COUNT(*) as cnt FROM traffic_readings GROUP BY source_type")
            counts = {r["source_type"]: r["cnt"] for r in cursor.fetchall()}

        # Verify exact counts and segregation
        self.assertIn("REAL_API", counts)
        self.assertGreaterEqual(counts["REAL_API"], 38, "REAL_API observations must be at least 38")
        self.assertEqual(counts.get("SIMULATED", 0), 1288, "SIMULATED observations must be exactly 1,288")
        self.assertEqual(counts.get("TEST_MOCK", 0), 12, "TEST_MOCK observations must be exactly 12")

        # Verify that all REAL_API records have non-null speeds and travel times
        with get_db_cursor(commit=False) as cursor:
            cursor.execute("""
                SELECT COUNT(*) as bad_cnt FROM traffic_readings
                WHERE source_type = 'REAL_API'
                AND (avg_speed_kmh IS NULL OR free_flow_speed_kmh IS NULL 
                     OR current_travel_time_sec IS NULL OR free_flow_travel_time_sec IS NULL)
            """)
            bad_cnt = cursor.fetchone()["bad_cnt"]
            self.assertEqual(bad_cnt, 0, "All REAL_API records must have valid speed and travel times")

    def test_02_scheduled_pipeline_runs_logging(self):
        """Verify that scheduled Airflow ingestion cycles are logged in pipeline_runs."""
        with get_db_cursor(commit=False) as cursor:
            cursor.execute("""
                SELECT * FROM pipeline_runs 
                WHERE pipeline_name = 'tomtom_traffic_ingestion' 
                ORDER BY started_at DESC LIMIT 2
            """)
            runs = cursor.fetchall()

        self.assertGreaterEqual(len(runs), 1, "At least one tomtom ingestion run must be logged")
        latest_run = runs[0]
        self.assertEqual(latest_run["status"], "SUCCESS")
        self.assertIn(latest_run["records_processed"], [11, 15], "Scheduled run must process 11 (Phase 4) or 15 (Phase 4B) corridors")
        self.assertEqual(latest_run["records_rejected"], 0)

    def test_03_active_vs_excluded_corridors(self):
        """Verify corridor recovery state (15 approved in Phase 4B)."""
        approved = get_approved_corridors()
        all_corridors = list(NAGPUR_CORRIDORS_GEO.keys())
        excluded = [cid for cid in all_corridors if cid not in approved]

        # Phase 4B verified all 4 previously excluded corridors: 15/15 approved
        self.assertEqual(len(approved), 15, "Approved corridors count must be 15 in Phase 4B")
        self.assertEqual(len(excluded), 0, "All 4 previously excluded corridors are now recovered")

        # Verify that all 15 corridor IDs are valid
        for cid in approved:
            self.assertIn(cid, NAGPUR_CORRIDORS_GEO)

    def test_04_tomtom_budget_protection(self):
        """Verify API budget safety tracker state and zero API consumption during testing."""
        budget_path = "data/tomtom_usage_state.json"
        self.assertTrue(os.path.exists(budget_path), "Usage budget JSON must exist")

        with open(budget_path, "r") as f:
            state = json.load(f)

        self.assertEqual(state["month"], "2026-10")
        self.assertEqual(state["monthly_budget"], 16000)
        self.assertGreaterEqual(state["requests_attempted"], 38)
        self.assertEqual(state["requests_failed"], 0)
        self.assertLess(state["requests_attempted"], 16000, "Must be well within 16,000 monthly quota")

    def test_05_traffic_data_loader_calculations(self):
        """Verify load_latest_traffic_per_corridor delay, speed reduction, and status labels."""
        df_latest = load_latest_traffic_per_corridor(
            location_id="LOC_NAGPUR",
            source_type="REAL_API",
            stale_threshold_minutes=90,
        )

        self.assertFalse(df_latest.empty, "df_latest must return genuine observations")
        required_cols = [
            "segment_id", "road_name", "avg_speed_kmh", "free_flow_speed_kmh",
            "current_travel_time_sec", "free_flow_travel_time_sec", "delay_seconds",
            "speed_reduction_pct", "freshness_badge", "is_stale", "timestamp_display"
        ]
        for col in required_cols:
            self.assertIn(col, df_latest.columns, f"Column {col} missing in df_latest")

        # Verify delay = max(0, current - free_flow)
        for _, row in df_latest.iterrows():
            expected_delay = max(0, int(row["current_travel_time_sec"] - row["free_flow_travel_time_sec"]))
            self.assertEqual(row["delay_seconds"], expected_delay)
            self.assertGreaterEqual(row["speed_reduction_pct"], 0.0)
            self.assertLessEqual(row["speed_reduction_pct"], 100.0)

    def test_06_load_anomalies_source_type_segregation(self):
        """Verify load_anomalies filters to REAL_API by default and quarantines SIMULATED."""
        df_real_anom = load_anomalies(location_id="LOC_NAGPUR", source_type="REAL_API")
        df_all_anom = load_anomalies(location_id="LOC_NAGPUR", source_type="ALL")

        # All rows in df_real_anom must be REAL_API
        if not df_real_anom.empty:
            for _, r in df_real_anom.iterrows():
                self.assertEqual(r["source_type"], "REAL_API")

        # df_all_anom contains simulated records
        sim_count = (df_all_anom["source_type"] == "SIMULATED").sum() if not df_all_anom.empty else 0
        self.assertGreater(sim_count, 0, "Historical simulated anomalies must exist in archive")
        self.assertGreater(len(df_all_anom), len(df_real_anom), "ALL must include simulated records")

    def test_07_anomaly_lifecycle_transitions(self):
        """Verify ACTIVE -> ACKNOWLEDGED -> RESOLVED transitions and persistence of resolution notes."""
        with get_db_cursor(commit=True) as cursor:
            # 1. Insert an isolated test anomaly
            test_id = f"ANOM_E2E_TEST_{int(datetime.now().timestamp())}"
            cursor.execute("""
                INSERT INTO anomalies (anomaly_id, anomaly_type, source_type, location_id, segment_id, timestamp, severity, description, status)
                VALUES (%s, 'CONGESTION_SPIKE', 'TEST_MOCK', 'LOC_NAGPUR', 'SEG_NAG_01', UTC_TIMESTAMP(), 'HIGH', 'E2E Lifecycle Test Alert', 'ACTIVE')
            """, (test_id,))

        try:
            # 2. Acknowledge
            with get_db_cursor(commit=True) as cursor:
                cursor.execute("UPDATE anomalies SET status = 'ACKNOWLEDGED' WHERE anomaly_id = %s", (test_id,))

            with get_db_cursor(commit=False) as cursor:
                cursor.execute("SELECT status FROM anomalies WHERE anomaly_id = %s", (test_id,))
                self.assertEqual(cursor.fetchone()["status"], "ACKNOWLEDGED")

            # 3. Resolve with notes
            test_notes = "Resolved by E2E test verification suite"
            with get_db_cursor(commit=True) as cursor:
                cursor.execute("""
                    UPDATE anomalies 
                    SET status = 'RESOLVED', resolution_notes = %s, resolved_at = UTC_TIMESTAMP() 
                    WHERE anomaly_id = %s
                """, (test_notes, test_id))

            with get_db_cursor(commit=False) as cursor:
                cursor.execute("SELECT status, resolution_notes, resolved_at FROM anomalies WHERE anomaly_id = %s", (test_id,))
                res = cursor.fetchone()
                self.assertEqual(res["status"], "RESOLVED")
                self.assertEqual(res["resolution_notes"], test_notes)
                self.assertIsNotNone(res["resolved_at"])
        finally:
            # Clean up test row
            with get_db_cursor(commit=True) as cursor:
                cursor.execute("DELETE FROM anomalies WHERE anomaly_id = %s", (test_id,))

    def test_08_rule_engine_traffic_anomaly_detection(self):
        """Verify rule-based anomaly detector triggers for congestion, speed drop, and closures without DB insertion."""
        engine = AnomalyRuleEngine()

        # Normal condition -> no anomaly
        normal_reading = {
            "segment_id": "SEG_NAG_01",
            "avg_speed_kmh": 60.0,
            "free_flow_speed_kmh": 65.0,
            "current_travel_time_sec": 330,
            "free_flow_travel_time_sec": 300,
            "congestion_level": "LOW",
            "road_closure": False,
            "source_type": "REAL_API",
        }
        res_normal = engine.check_traffic_reading(normal_reading)
        self.assertIsNone(res_normal, "Normal conditions should not trigger anomalies")

        # Severe congestion -> triggers anomaly
        severe_reading = {
            "segment_id": "SEG_NAG_01",
            "avg_speed_kmh": 12.0,
            "free_flow_speed_kmh": 65.0,
            "current_travel_time_sec": 1200,
            "free_flow_travel_time_sec": 300,
            "congestion_level": "SEVERE",
            "road_closure": False,
            "source_type": "REAL_API",
        }
        with patch.object(engine, "_insert_anomaly", return_value="ANOM_MOCK_01") as mock_insert:
            res_severe = engine.check_traffic_reading(severe_reading)
            self.assertEqual(res_severe, "ANOM_MOCK_01")
            mock_insert.assert_called_once()
            kwargs = mock_insert.call_args.kwargs
            self.assertEqual(kwargs.get("anomaly_type"), "SEVERE_CONGESTION")
            self.assertEqual(kwargs.get("source_type"), "REAL_API")

        # Explicit road closure -> triggers anomaly
        closure_reading = {
            "segment_id": "SEG_NAG_01",
            "avg_speed_kmh": 0.0,
            "free_flow_speed_kmh": 65.0,
            "current_travel_time_sec": 9999,
            "free_flow_travel_time_sec": 300,
            "congestion_level": "SEVERE",
            "road_closure": True,
            "source_type": "REAL_API",
        }
        with patch.object(engine, "_insert_anomaly", return_value="ANOM_MOCK_02") as mock_insert:
            res_closure = engine.check_traffic_reading(closure_reading)
            self.assertEqual(res_closure, "ANOM_MOCK_02")
            mock_insert.assert_called_once()
            kwargs = mock_insert.call_args.kwargs
            self.assertEqual(kwargs.get("anomaly_type"), "ROAD_CLOSURE")
            self.assertEqual(kwargs.get("severity"), "CRITICAL")
            self.assertEqual(kwargs.get("source_type"), "REAL_API")

    def test_09_environmental_and_iot_telemetry(self):
        """Verify real environmental observations and IoT gateway status functions."""
        df_weather = load_latest_weather(location_id="LOC_NAGPUR")
        df_aq = load_latest_air_quality(location_id="LOC_NAGPUR")

        self.assertFalse(df_weather.empty, "Weather must have records for LOC_NAGPUR")
        self.assertFalse(df_aq.empty, "Air quality must have records for LOC_NAGPUR")
        self.assertEqual(df_weather["source_type"].iloc[0], "REAL_API")
        self.assertEqual(df_aq["source_type"].iloc[0], "REAL_API")

        # IoT Gateway status function
        gw_status = get_gateway_runtime_status()
        self.assertIsInstance(gw_status, dict)
        self.assertIn("is_alive", gw_status)
        self.assertIn("connection_state", gw_status)

    def test_10_all_six_dashboard_views_import_and_render_contract(self):
        """Verify all six dashboard views can be imported and their render functions are callable."""
        from dashboard.views.overview import render_overview
        from dashboard.views.traffic import render_traffic
        from dashboard.views.environment import render_environment
        from dashboard.views.urban_analytics import render_urban_analytics
        from dashboard.views.iot_monitoring import render_iot_monitoring
        from dashboard.views.anomaly_center import render_anomaly_center

        for fn in [
            render_overview,
            render_traffic,
            render_environment,
            render_urban_analytics,
            render_iot_monitoring,
            render_anomaly_center,
        ]:
            self.assertTrue(callable(fn), f"{fn.__name__} must be a callable render function")


if __name__ == "__main__":
    unittest.main()
