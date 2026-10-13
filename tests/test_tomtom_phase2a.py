"""
Comprehensive Unit and Regression Test Suite for TomTom Traffic Integration Phase 2A.
All external HTTP requests are mocked to preserve real API request quota.
"""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from config.corridors import NAGPUR_CORRIDORS_GEO, get_corridor_geo
from ingestion.traffic.tomtom_client import TomTomBudgetTracker, TomTomTrafficClient
from validation.models import TrafficRecord
from validation.validator import ValidationEngine


class TestTomTomPhase2A(unittest.TestCase):
    def setUp(self):
        # Create a temporary state file for budget testing
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temp_dir.name) / "test_tomtom_state.json"
        self.budget_tracker = TomTomBudgetTracker(
            state_file=self.state_file, monthly_budget=10
        )
        self.client = TomTomTrafficClient(api_key="TEST_MOCK_KEY_XYZ")
        self.client.budget_tracker = self.budget_tracker
        self.patch_repo = patch("ingestion.traffic.tomtom_client.repository")
        self.mock_repo = self.patch_repo.start()
        self.patch_arch = patch("ingestion.traffic.tomtom_client.archiver")
        self.mock_arch = self.patch_arch.start()

    def tearDown(self):
        self.patch_repo.stop()
        self.patch_arch.stop()
        self.temp_dir.cleanup()

    def test_corridor_registry_completeness(self):
        """Verify all 15 registered Nagpur corridors exist with valid coordinates."""
        self.assertEqual(len(NAGPUR_CORRIDORS_GEO), 15)
        for i in range(1, 16):
            sid = f"SEG_NAG_{i:02d}"
            corridor = get_corridor_geo(sid)
            self.assertIsNotNone(corridor, f"Corridor {sid} missing from registry")
            lat = corridor["latitude"]
            lon = corridor["longitude"]
            # Latitude within Nagpur bounding box (~21.0 to 21.25)
            self.assertTrue(21.0 <= lat <= 21.25, f"{sid} lat {lat} out of bounds")
            # Longitude within Nagpur bounding box (~79.0 to 79.15)
            self.assertTrue(79.0 <= lon <= 79.15, f"{sid} lon {lon} out of bounds")
            self.assertTrue(corridor["speed_limit_kmh"] > 0)
            self.assertTrue(corridor["length_km"] > 0)

    def test_budget_tracker_initial_state(self):
        """Verify initial budget state starts clean."""
        usage = self.budget_tracker.get_usage()
        self.assertEqual(usage["requests_attempted"], 0)
        self.assertEqual(usage["requests_successful"], 0)
        self.assertEqual(usage["requests_failed"], 0)
        self.assertEqual(usage["monthly_budget"], 10)
        can_req, _ = self.budget_tracker.can_request()
        self.assertTrue(can_req)

    def test_budget_tracker_records_attempts_accurately(self):
        """Verify request counter increments correctly for success and failure."""
        self.budget_tracker.record_attempt(successful=True)
        self.budget_tracker.record_attempt(successful=False)
        usage = self.budget_tracker.get_usage()
        self.assertEqual(usage["requests_attempted"], 2)
        self.assertEqual(usage["requests_successful"], 1)
        self.assertEqual(usage["requests_failed"], 1)
        self.assertIsNotNone(usage["last_request_timestamp"])

    def test_budget_cutoff_enforcement(self):
        """Verify request is refused when monthly budget is reached."""
        for _ in range(10):
            self.budget_tracker.record_attempt(successful=True)
        can_req, msg = self.budget_tracker.can_request()
        self.assertFalse(can_req)
        self.assertIn("safety cutoff engaged", msg)

    @patch("requests.get")
    def test_client_respects_budget_cutoff_without_http(self, mock_get):
        """Verify client does not execute HTTP request when budget is exhausted."""
        for _ in range(10):
            self.budget_tracker.record_attempt(successful=True)
        ok, payload, err = self.client.fetch_flow_segment_data(21.0895, 79.0645)
        self.assertFalse(ok)
        self.assertIsNone(payload)
        self.assertIn("safety cutoff", err)
        mock_get.assert_not_called()

    @patch("requests.get")
    def test_client_successful_flow_parse(self, mock_get):
        """Verify successful response parsing and normalization."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "flowSegmentData": {
                "frc": "FRC1",
                "currentSpeed": 45,
                "freeFlowSpeed": 60,
                "currentTravelTime": 180,
                "freeFlowTravelTime": 140,
                "confidence": 0.95,
                "roadClosure": False,
            }
        }
        mock_get.return_value = mock_resp

        ok, rec, err = self.client.ingest_segment("SEG_NAG_02")
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertEqual(rec.segment_id, "SEG_NAG_02")
        self.assertEqual(rec.avg_speed_kmh, 45.0)
        self.assertEqual(rec.free_flow_speed_kmh, 60.0)
        self.assertEqual(rec.current_travel_time_sec, 180)
        self.assertEqual(rec.free_flow_travel_time_sec, 140)
        self.assertEqual(rec.confidence_score, 0.95)
        self.assertFalse(rec.road_closure)
        self.assertEqual(rec.congestion_level, "LOW")  # 45/60 = 0.75 -> >= 0.75 is LOW
        self.assertEqual(rec.source_type, "REAL_API")
        self.assertIsNone(rec.vehicle_count)
        self.assertIsNone(rec.traffic_density_vpk)

    @patch("requests.get")
    def test_partial_batch_failure_resilience(self, mock_get):
        """Verify failure on one corridor does not prevent others from succeeding."""
        def side_effect(*args, **kwargs):
            point = kwargs.get("params", {}).get("point", "")
            resp = MagicMock()
            # Simulate failure on Sitabuldi (SEG_NAG_02)
            from config.corridors import get_corridor_geo
            s02_lat = str(get_corridor_geo("SEG_NAG_02")["latitude"])
            if s02_lat in point or "21.1462" in point:
                resp.status_code = 500
                resp.text = "Internal Server Error"
                return resp
            resp.status_code = 200
            resp.json.return_value = {
                "flowSegmentData": {
                    "currentSpeed": 50,
                    "freeFlowSpeed": 60,
                    "currentTravelTime": 120,
                    "freeFlowTravelTime": 100,
                    "confidence": 1.0,
                    "roadClosure": False,
                }
            }
            return resp

        mock_get.side_effect = side_effect

        targets = ["SEG_NAG_01", "SEG_NAG_02", "SEG_NAG_03"]
        results = self.client.ingest_all_corridors(corridor_ids=targets)

        self.assertEqual(results["total_corridors"], 3)
        self.assertEqual(results["successful"], 2)
        self.assertEqual(results["failed"], 1)
        self.assertIn("SEG_NAG_01", results["successful_segments"])
        self.assertIn("SEG_NAG_03", results["successful_segments"])
        self.assertIn("SEG_NAG_02", results["failed_segments"])

    def test_airflow_dag_import(self):
        """Verify Airflow DAG file can be imported without syntax or dependency errors."""
        import airflow.dags.urbanpulse_tomtom_traffic_dag as dag_module
        self.assertTrue(hasattr(dag_module, "task_ingest_tomtom_traffic"))


if __name__ == "__main__":
    unittest.main()
