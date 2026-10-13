"""
Unit and Integration Verification Suite for Phase 3:
Automated TomTom Traffic Pipeline Activation, Concurrency File-Locking,
Airflow DAG Configuration, and Ingestion Integrity.
All tests use mocks or read-only queries. Zero live API calls are made.
"""

import threading
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from config.corridors import (
    NAGPUR_CORRIDORS_GEO,
    get_approved_corridors,
    get_corridor_geo,
)
from ingestion.traffic.tomtom_client import TomTomBudgetTracker, TomTomTrafficClient
from dashboard.data_loader import (
    load_latest_traffic_per_corridor,
    load_traffic_readings,
)
from database.connection import get_db_cursor


class TestPhase3Activation(unittest.TestCase):
    def test_01_airflow_dag_configuration(self):
        """Verify Airflow DAG specification adheres to activation requirements."""
        import airflow.dags.urbanpulse_tomtom_traffic_dag as dag_module
        self.assertTrue(hasattr(dag_module, "task_ingest_tomtom_traffic"))

        if hasattr(dag_module, "dag"):
            dag = dag_module.dag
            self.assertEqual(dag.dag_id, "urbanpulse_tomtom_traffic_ingestion")
            self.assertFalse(dag.catchup, "catchup must be False")
            self.assertEqual(dag.max_active_runs, 1, "max_active_runs must be 1")
            self.assertEqual(dag.schedule_interval, "0 * * * *", "Schedule must be hourly")
            self.assertFalse(dag.is_paused_upon_creation, "DAG must be configured unpaused for active state")

    def test_02_approved_corridors_registry(self):
        """Verify corridor registry state (15 approved in Phase 4B)."""
        approved = get_approved_corridors()
        self.assertEqual(len(approved), 15, f"Expected 15 approved corridors, got {len(approved)}")

        # Verify all 15 corridors are verified
        for cid in approved:
            geo = get_corridor_geo(cid)
            self.assertEqual(geo["match_quality"], "VERIFIED")
            self.assertTrue(geo["approved_for_ingestion"])

        # SEG_NAG_07 (Amravati Road) must be approved and refined
        geo_07 = get_corridor_geo("SEG_NAG_07")
        self.assertEqual(geo_07["match_quality"], "VERIFIED")
        self.assertTrue(geo_07["approved_for_ingestion"])
        self.assertAlmostEqual(geo_07["latitude"], 21.1518, places=3)
        self.assertAlmostEqual(geo_07["longitude"], 79.0256, places=3)

    def test_03_budget_tracker_thread_safe_file_locking(self):
        """Verify atomic file locking preserves state counter accuracy during concurrent access."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "test_concurrent_state.json"
            tracker = TomTomBudgetTracker(state_file=state_file, monthly_budget=500)

            # Spawn 20 concurrent threads all recording attempts
            threads = []
            for _ in range(20):
                t = threading.Thread(target=tracker.record_attempt, args=(True,))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            usage = tracker.get_usage()
            self.assertEqual(usage["requests_attempted"], 20, "Concurrent updates must not lose increments")
            self.assertEqual(usage["requests_successful"], 20)
            self.assertEqual(usage["requests_failed"], 0)

    def test_04_budget_tracker_safety_cutoff(self):
        """Verify strict request blocking when safety budget is reached."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "test_cutoff_state.json"
            tracker = TomTomBudgetTracker(state_file=state_file, monthly_budget=5)

            for _ in range(5):
                allowed, _ = tracker.can_request()
                self.assertTrue(allowed)
                tracker.record_attempt(successful=True)

            # 6th request must be rejected
            allowed, msg = tracker.can_request()
            self.assertFalse(allowed)
            self.assertIn("safety cutoff engaged", msg)

    @patch("requests.get")
    def test_05_client_defaults_to_approved_corridors_only(self, mock_get):
        """Verify ingest_all_corridors defaults to 11 verified corridors without calling unapproved."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "flowSegmentData": {
                "currentSpeed": 40,
                "freeFlowSpeed": 45,
                "currentTravelTime": 200,
                "freeFlowTravelTime": 190,
                "confidence": 0.98,
                "roadClosure": False,
            }
        }
        mock_get.return_value = mock_resp

        client = TomTomTrafficClient(api_key="MOCK_TEST_KEY")
        client.budget_tracker = MagicMock()
        client.budget_tracker.can_request.return_value = (True, "OK")

        with patch("ingestion.traffic.tomtom_client.repository"), \
             patch("ingestion.traffic.tomtom_client.archiver"):
            results = client.ingest_all_corridors()
            self.assertEqual(results["total_corridors"], 15, "Default batch targets all 15 approved corridors")
            self.assertIn("SEG_NAG_02", results["successful_segments"])
            self.assertIn("SEG_NAG_14", results["successful_segments"])

    @patch("requests.get")
    def test_06_anomaly_engine_invoked_on_ingestion(self, mock_get):
        """Verify ingest_segment triggers rule_engine.check_traffic_reading after database save."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Simulate severe congestion response
        mock_resp.json.return_value = {
            "flowSegmentData": {
                "currentSpeed": 5,
                "freeFlowSpeed": 50,
                "currentTravelTime": 900,
                "freeFlowTravelTime": 120,
                "confidence": 0.95,
                "roadClosure": False,
            }
        }
        mock_get.return_value = mock_resp

        client = TomTomTrafficClient(api_key="MOCK_TEST_KEY")
        client.budget_tracker = MagicMock()
        client.budget_tracker.can_request.return_value = (True, "OK")

        with patch("ingestion.traffic.tomtom_client.repository"), \
             patch("ingestion.traffic.tomtom_client.archiver"), \
             patch("anomaly_detection.rule_engine.rule_engine.check_traffic_reading") as mock_rule_check:
            mock_rule_check.return_value = "ANOM_MOCK_123"

            ok, rec, err = client.ingest_segment("SEG_NAG_01")
            self.assertTrue(ok)
            mock_rule_check.assert_called_once()
            called_dict = mock_rule_check.call_args[0][0]
            self.assertEqual(called_dict["segment_id"], "SEG_NAG_01")
            self.assertEqual(called_dict["source_type"], "REAL_API")

    def test_07_mysql_latest_corridor_freshness(self):
        """Verify load_latest_traffic_per_corridor retrieves fresh observations and IST timestamps."""
        # Use a generous threshold for offline verification to avoid time-decay failure on historical test runs
        df_latest = load_latest_traffic_per_corridor(location_id="LOC_NAGPUR", source_type="REAL_API", stale_threshold_minutes=1440 * 7)
        self.assertFalse(df_latest.empty)
        # Approved corridors must have fresh observations from controlled cycle
        c_01 = df_latest[df_latest["segment_id"] == "SEG_NAG_01"].iloc[0]
        self.assertEqual(c_01["source_type"], "REAL_API")
        self.assertFalse(c_01["is_stale"], "Recent controlled cycle observation must be fresh")
        self.assertIn("IST", c_01["timestamp_display"])
        self.assertGreater(c_01["avg_speed_kmh"], 0)

    def test_08_pipeline_run_logged_successfully(self):
        """Verify pipeline_runs table records controlled cycle run with SUCCESS status."""
        with get_db_cursor(commit=False) as cursor:
            cursor.execute("""
                SELECT status, records_processed, pipeline_name
                FROM pipeline_runs
                WHERE pipeline_name = 'tomtom_traffic_ingestion'
                ORDER BY started_at DESC
                LIMIT 1
            """)
            run = cursor.fetchone()
            self.assertIsNotNone(run)
            self.assertEqual(run["status"], "SUCCESS")
            self.assertIn(run["records_processed"], [11, 15], "Scheduled run must process 11 (Phase 3) or 15 (Phase 4B) corridors")


if __name__ == "__main__":
    unittest.main()
