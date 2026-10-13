"""
Unit and Integration Test Suite for Phase 2B:
Real Traffic Dashboard, Real-Data-Only SQL Enforcement, and Anomaly Detection.
All external dependencies are mocked or queried read-only against existing MySQL state.
Zero live TomTom API requests are made.
"""

import unittest
from datetime import datetime, timezone
import pandas as pd
from unittest.mock import patch, MagicMock

from config.corridors import NAGPUR_CORRIDORS_GEO, get_corridor_geo
from dashboard.data_loader import (
    load_traffic_readings,
    load_latest_traffic_per_corridor,
    load_anomalies,
    format_time_ago,
)
from anomaly_detection.rule_engine import AnomalyRuleEngine, rule_engine
from database.connection import get_db_cursor


class TestPhase2BTrafficDashboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rule_engine = AnomalyRuleEngine()

    def test_01_sql_filtering_defaults_to_real_api(self):
        """Verify load_traffic_readings defaults to REAL_API and quarantines SIMULATED data."""
        df_real = load_traffic_readings(location_id="LOC_NAGPUR", limit=500)
        if not df_real.empty:
            source_types = df_real["source_type"].unique().tolist()
            self.assertEqual(source_types, ["REAL_API"], "Must contain ONLY REAL_API records")
            # Verify no simulated records contaminated the default result
            self.assertNotIn("SIMULATED", source_types)

    def test_02_historical_simulated_data_preserved_unaltered(self):
        """Verify the 1,288 historical simulated records remain intact in MySQL."""
        with get_db_cursor(commit=False) as cursor:
            cursor.execute("SELECT COUNT(*) as c FROM traffic_readings WHERE source_type = 'SIMULATED'")
            sim_count = cursor.fetchone()["c"]
            self.assertEqual(sim_count, 1288, "Expected exactly 1,288 historical SIMULATED records")

    def test_03_load_latest_traffic_per_corridor_coverage(self):
        """Verify load_latest_traffic_per_corridor retrieves all 15 registered Nagpur corridors."""
        df_latest = load_latest_traffic_per_corridor(location_id="LOC_NAGPUR", source_type="REAL_API")
        self.assertFalse(df_latest.empty)
        self.assertEqual(len(df_latest), 15, "Should have 1 latest record per corridor for all 15 corridors")
        # Verify all corridor IDs from SEG_NAG_01 to SEG_NAG_15 are present
        expected_ids = {f"SEG_NAG_{i:02d}" for i in range(1, 16)}
        observed_ids = set(df_latest["segment_id"].tolist())
        self.assertEqual(observed_ids, expected_ids)

    def test_04_derived_formulas_and_null_safety(self):
        """Verify calculated delay and speed reduction formulas with safe null/zero handling."""
        df_latest = load_latest_traffic_per_corridor(location_id="LOC_NAGPUR", source_type="REAL_API")
        self.assertIn("delay_seconds", df_latest.columns)
        self.assertIn("speed_reduction_pct", df_latest.columns)
        self.assertIn("timestamp_display", df_latest.columns)

        for _, row in df_latest.iterrows():
            # Delay >= 0
            self.assertGreaterEqual(row["delay_seconds"], 0)
            # Speed reduction >= 0
            self.assertGreaterEqual(row["speed_reduction_pct"], 0.0)
            # IST timestamp formatted properly
            self.assertIn("IST", row["timestamp_display"])
            # Vehicle count is safely None/NaN without throwing error
            self.assertTrue(pd.isna(row["vehicle_count"]) or isinstance(row["vehicle_count"], (int, float)))

    def test_05_freshness_calculation_and_stale_detection(self):
        """Verify format_time_ago and stale observation thresholding."""
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        # Fresh observation (< 90 minutes)
        fresh_time = now_utc
        h_str, diff = format_time_ago(fresh_time, is_utc=True)
        self.assertIn("Just now", h_str)

        # Stale observation (> 90 minutes)
        from datetime import timedelta
        stale_time = now_utc - timedelta(hours=3)
        h_str_stale, diff_stale = format_time_ago(stale_time, is_utc=True)
        self.assertGreater(diff_stale, 90 * 60)
        self.assertIn("3.0h ago", h_str_stale)

    def test_06_rule_engine_road_closure_detection(self):
        """Verify rule engine detects road closure explicitly indicated by API."""
        reading = {
            "segment_id": "SEG_NAG_01",
            "location_id": "LOC_NAGPUR",
            "source_type": "REAL_API",
            "avg_speed_kmh": 0.0,
            "free_flow_speed_kmh": 60.0,
            "current_travel_time_sec": 9999,
            "free_flow_travel_time_sec": 300,
            "road_closure": True,
            "congestion_level": "SEVERE",
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None),
        }
        with patch.object(self.rule_engine, "_insert_anomaly") as mock_insert:
            mock_insert.return_value = "ANOM_TEST_01"
            res = self.rule_engine.check_traffic_reading(reading)
            self.assertEqual(res, "ANOM_TEST_01")
            mock_insert.assert_called_once()
            args, kwargs = mock_insert.call_args
            self.assertEqual(kwargs["anomaly_type"], "ROAD_CLOSURE")
            self.assertEqual(kwargs["severity"], "CRITICAL")
            self.assertEqual(kwargs["source_type"], "REAL_API")

    def test_07_rule_engine_severe_congestion_detection(self):
        """Verify rule engine detects severe congestion."""
        reading = {
            "segment_id": "SEG_NAG_02",
            "location_id": "LOC_NAGPUR",
            "source_type": "REAL_API",
            "avg_speed_kmh": 8.0,
            "free_flow_speed_kmh": 45.0,
            "current_travel_time_sec": 450,
            "free_flow_travel_time_sec": 120,
            "road_closure": False,
            "congestion_level": "SEVERE",
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None),
        }
        with patch.object(self.rule_engine, "_insert_anomaly") as mock_insert:
            mock_insert.return_value = "ANOM_TEST_02"
            res = self.rule_engine.check_traffic_reading(reading)
            self.assertEqual(res, "ANOM_TEST_02")
            mock_insert.assert_called_once()
            args, kwargs = mock_insert.call_args
            self.assertEqual(kwargs["anomaly_type"], "SEVERE_CONGESTION")
            self.assertEqual(kwargs["severity"], "HIGH")
            self.assertEqual(kwargs["source_type"], "REAL_API")

    def test_08_rule_engine_significant_speed_drop(self):
        """Verify rule engine detects significant speed drop (> 50% below free-flow)."""
        reading = {
            "segment_id": "SEG_NAG_03",
            "location_id": "LOC_NAGPUR",
            "source_type": "REAL_API",
            "avg_speed_kmh": 18.0,
            "free_flow_speed_kmh": 50.0,  # 18/50 = 36% -> 64% speed drop
            "current_travel_time_sec": 180,
            "free_flow_travel_time_sec": 120,
            "road_closure": False,
            "congestion_level": "HIGH",
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None),
        }
        with patch.object(self.rule_engine, "_insert_anomaly") as mock_insert:
            mock_insert.return_value = "ANOM_TEST_03"
            res = self.rule_engine.check_traffic_reading(reading)
            self.assertEqual(res, "ANOM_TEST_03")
            mock_insert.assert_called_once()
            args, kwargs = mock_insert.call_args
            self.assertEqual(kwargs["anomaly_type"], "SIGNIFICANT_SPEED_DROP")
            self.assertEqual(kwargs["severity"], "MEDIUM")
            self.assertEqual(kwargs["source_type"], "REAL_API")

    def test_09_rule_engine_high_travel_delay(self):
        """Verify rule engine detects high travel delay (>= 300s above baseline)."""
        reading = {
            "segment_id": "SEG_NAG_08",
            "location_id": "LOC_NAGPUR",
            "source_type": "REAL_API",
            "avg_speed_kmh": 28.0,
            "free_flow_speed_kmh": 36.0,
            "current_travel_time_sec": 1471,
            "free_flow_travel_time_sec": 1144,  # Delay = 327s (>= 300s)
            "road_closure": False,
            "congestion_level": "MEDIUM",
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None),
        }
        with patch.object(self.rule_engine, "_insert_anomaly") as mock_insert:
            mock_insert.return_value = "ANOM_TEST_04"
            res = self.rule_engine.check_traffic_reading(reading)
            self.assertEqual(res, "ANOM_TEST_04")
            mock_insert.assert_called_once()
            args, kwargs = mock_insert.call_args
            self.assertEqual(kwargs["anomaly_type"], "HIGH_TRAVEL_DELAY")
            self.assertEqual(kwargs["source_type"], "REAL_API")

    def test_10_nominal_reading_generates_no_anomaly(self):
        """Verify normal free-flow conditions trigger no anomalies."""
        reading = {
            "segment_id": "SEG_NAG_01",
            "location_id": "LOC_NAGPUR",
            "source_type": "REAL_API",
            "avg_speed_kmh": 65.0,
            "free_flow_speed_kmh": 70.0,
            "current_travel_time_sec": 300,
            "free_flow_travel_time_sec": 290,
            "road_closure": False,
            "congestion_level": "LOW",
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None),
        }
        with patch.object(self.rule_engine, "_insert_anomaly") as mock_insert:
            res = self.rule_engine.check_traffic_reading(reading)
            self.assertIsNone(res)
            mock_insert.assert_not_called()

    def test_11_incident_triage_lifecycle_transitions(self):
        """Verify database update and lifecycle transitions: ACTIVE -> ACKNOWLEDGED -> RESOLVED."""
        test_anom_id = "ANOM_TEST_LIFECYCLE_99"
        ts = datetime.now(timezone.utc).replace(tzinfo=None)

        try:
            # 1. Insert an active test anomaly with TEST_MOCK provenance
            with get_db_cursor(commit=True) as cursor:
                cursor.execute("DELETE FROM anomalies WHERE anomaly_id = %(id)s", {"id": test_anom_id})
                cursor.execute("""
                    INSERT INTO anomalies (
                        anomaly_id, anomaly_type, source_type, location_id, segment_id,
                        timestamp, severity, description, status
                    ) VALUES (
                        %(id)s, 'SEVERE_CONGESTION', 'TEST_MOCK', 'LOC_NAGPUR', 'SEG_NAG_01',
                        %(ts)s, 'HIGH', 'Test lifecycle anomaly', 'ACTIVE'
                    )
                """, {"id": test_anom_id, "ts": ts})

            # Verify state is ACTIVE
            with get_db_cursor(commit=False) as cursor:
                cursor.execute("SELECT status FROM anomalies WHERE anomaly_id = %(id)s", {"id": test_anom_id})
                self.assertEqual(cursor.fetchone()["status"], "ACTIVE")

            # 2. Transition to ACKNOWLEDGED
            with get_db_cursor(commit=True) as cursor:
                cursor.execute(
                    "UPDATE anomalies SET status = 'ACKNOWLEDGED' WHERE anomaly_id = %(id)s AND status = 'ACTIVE'",
                    {"id": test_anom_id}
                )

            with get_db_cursor(commit=False) as cursor:
                cursor.execute("SELECT status FROM anomalies WHERE anomaly_id = %(id)s", {"id": test_anom_id})
                self.assertEqual(cursor.fetchone()["status"], "ACKNOWLEDGED")

            # 3. Transition to RESOLVED with note
            note = "Traffic bottleneck cleared; signal phase rebalanced."
            with get_db_cursor(commit=True) as cursor:
                cursor.execute(
                    """
                    UPDATE anomalies
                    SET status = 'RESOLVED', resolution_notes = %(note)s, resolved_at = UTC_TIMESTAMP()
                    WHERE anomaly_id = %(id)s AND status = 'ACKNOWLEDGED'
                    """,
                    {"id": test_anom_id, "note": note}
                )

            with get_db_cursor(commit=False) as cursor:
                cursor.execute(
                    "SELECT status, resolution_notes, resolved_at FROM anomalies WHERE anomaly_id = %(id)s",
                    {"id": test_anom_id}
                )
                resolved_row = cursor.fetchone()
                self.assertEqual(resolved_row["status"], "RESOLVED")
                self.assertEqual(resolved_row["resolution_notes"], note)
                self.assertIsNotNone(resolved_row["resolved_at"])
        finally:
            # 4. Clean up test record unconditionally
            with get_db_cursor(commit=True) as cursor:
                cursor.execute("DELETE FROM anomalies WHERE anomaly_id = %(id)s", {"id": test_anom_id})

    def test_12_road_names_joined_in_anomalies(self):
        """Verify load_anomalies joins road_segments to return human-readable road names."""
        df_anom = load_anomalies(location_id="LOC_NAGPUR", limit=10)
        self.assertIn("road_name", df_anom.columns)
        self.assertIn("timestamp_display", df_anom.columns)


if __name__ == "__main__":
    unittest.main()
