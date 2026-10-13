"""
UrbanPulse NEXUS — Regression Test Suite for Traffic Rollup Calculations.
Tests:
1. Hourly traffic rollups with entirely unmeasured (NULL) vehicle counts (genuine TomTom REAL_API).
2. Semantic preservation of NULL vehicle counts (no fabrication, no zero-filling).
3. Mixed observations (averaging only over known vehicle counts, ignoring NULLs without treating them as 0).
4. Auto-healing on schema 1048 'cannot be null' constraint.
5. Error visibility in the batch orchestrator (prevents silent reporting of SUCCESS on rollup failure).
6. Live execution against local MySQL.
"""

import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

from analytics.traffic_analytics import traffic_analytics, TrafficAnalytics
from scripts.run_scheduled_batch import run_live_scheduled_batch


class TestTrafficRollupsRegression(unittest.TestCase):

    def test_rollup_with_all_null_vehicle_counts_preserves_null(self):
        """
        Verifies that when all observations in an hour bucket lack vehicle counts
        (as with genuine TomTom Flow API), avg_vehicle_count and peak_vehicle_count
        are strictly stored as NULL (Python None), without fabricating counts or zero-filling.
        """
        mock_data = pd.DataFrame([
            {
                "event_id": "EVT_TRF_TEST_01",
                "sensor_id": "SNS_TRF_NAG_01",
                "segment_id": "SEG_NAG_01",
                "timestamp": pd.Timestamp("2026-10-13 14:15:00"),
                "vehicle_count": None,
                "avg_speed_kmh": 32.5,
                "free_flow_speed_kmh": 50.0,
                "current_travel_time_sec": 120,
                "free_flow_travel_time_sec": 100,
                "confidence_score": 0.9,
                "road_closure": False,
                "congestion_level": "LOW",
                "traffic_density_vpk": None,
                "source_type": "REAL_API",
                "road_name": "Wardha Road",
            },
            {
                "event_id": "EVT_TRF_TEST_02",
                "sensor_id": "SNS_TRF_NAG_01",
                "segment_id": "SEG_NAG_01",
                "timestamp": pd.Timestamp("2026-10-13 14:45:00"),
                "vehicle_count": None,
                "avg_speed_kmh": 27.5,
                "free_flow_speed_kmh": 50.0,
                "current_travel_time_sec": 140,
                "free_flow_travel_time_sec": 100,
                "confidence_score": 0.9,
                "road_closure": False,
                "congestion_level": "MEDIUM",
                "traffic_density_vpk": None,
                "source_type": "REAL_API",
                "road_name": "Wardha Road",
            },
        ])

        with patch.object(TrafficAnalytics, "load_traffic_dataframe", return_value=mock_data):
            with patch("analytics.traffic_analytics.get_db_cursor") as mock_cursor_ctx:
                mock_cursor = MagicMock()
                mock_cursor_ctx.return_value.__enter__.return_value = mock_cursor

                count = traffic_analytics.compute_and_store_hourly_metrics()
                self.assertEqual(count, 1)

                # Inspect parameters passed to cursor.execute
                mock_cursor.execute.assert_called_once()
                call_args = mock_cursor.execute.call_args[0]
                row_dict = call_args[1]

                self.assertEqual(row_dict["segment_id"], "SEG_NAG_01")
                self.assertEqual(row_dict["hour_bucket"], datetime(2026, 10, 13, 14, 0))
                # Must be None (SQL NULL), never 0 or fabricated
                self.assertIsNone(row_dict["avg_vehicle_count"], "avg_vehicle_count must be None when unobserved")
                self.assertIsNone(row_dict["peak_vehicle_count"], "peak_vehicle_count must be None when unobserved")
                # Derived speed and congestion must be calculated accurately
                self.assertEqual(row_dict["avg_speed_kmh"], 30.0)
                self.assertEqual(row_dict["congestion_index"], 1.5)
                self.assertEqual(row_dict["sample_count"], 2)

    def test_rollup_with_mixed_observations_computes_mean_over_known_values(self):
        """
        Verifies that when some readings have vehicle counts and some do not,
        the mean and max are computed strictly over the known values without
        treating missing values as 0.
        """
        mock_data = pd.DataFrame([
            {
                "event_id": "EVT_TRF_TEST_03",
                "sensor_id": "SNS_TRF_NAG_02",
                "segment_id": "SEG_NAG_02",
                "timestamp": pd.Timestamp("2026-10-13 15:10:00"),
                "vehicle_count": 60,
                "avg_speed_kmh": 40.0,
                "free_flow_speed_kmh": 50.0,
                "current_travel_time_sec": 100,
                "free_flow_travel_time_sec": 100,
                "confidence_score": 0.95,
                "road_closure": False,
                "congestion_level": "LOW",
                "traffic_density_vpk": 20.0,
                "source_type": "SIMULATED",
                "road_name": "Amravati Road",
            },
            {
                "event_id": "EVT_TRF_TEST_04",
                "sensor_id": "SNS_TRF_NAG_02",
                "segment_id": "SEG_NAG_02",
                "timestamp": pd.Timestamp("2026-10-13 15:20:00"),
                "vehicle_count": None,  # Unmeasured
                "avg_speed_kmh": 42.0,
                "free_flow_speed_kmh": 50.0,
                "current_travel_time_sec": 95,
                "free_flow_travel_time_sec": 100,
                "confidence_score": 0.90,
                "road_closure": False,
                "congestion_level": "LOW",
                "traffic_density_vpk": None,
                "source_type": "REAL_API",
                "road_name": "Amravati Road",
            },
            {
                "event_id": "EVT_TRF_TEST_05",
                "sensor_id": "SNS_TRF_NAG_02",
                "segment_id": "SEG_NAG_02",
                "timestamp": pd.Timestamp("2026-10-13 15:40:00"),
                "vehicle_count": 80,
                "avg_speed_kmh": 38.0,
                "free_flow_speed_kmh": 50.0,
                "current_travel_time_sec": 110,
                "free_flow_travel_time_sec": 100,
                "confidence_score": 0.95,
                "road_closure": False,
                "congestion_level": "LOW",
                "traffic_density_vpk": 25.0,
                "source_type": "SIMULATED",
                "road_name": "Amravati Road",
            },
        ])

        with patch.object(TrafficAnalytics, "load_traffic_dataframe", return_value=mock_data):
            with patch("analytics.traffic_analytics.get_db_cursor") as mock_cursor_ctx:
                mock_cursor = MagicMock()
                mock_cursor_ctx.return_value.__enter__.return_value = mock_cursor

                count = traffic_analytics.compute_and_store_hourly_metrics()
                self.assertEqual(count, 1)

                call_args = mock_cursor.execute.call_args[0]
                row_dict = call_args[1]

                # Mean of [60, 80] = 70.0 (if None was treated as 0, it would be 46.67)
                self.assertEqual(row_dict["avg_vehicle_count"], 70.0)
                self.assertEqual(row_dict["peak_vehicle_count"], 80)
                self.assertEqual(row_dict["avg_speed_kmh"], 40.0)
                self.assertEqual(row_dict["sample_count"], 3)

    def test_schema_compatibility_auto_heal_on_1048(self):
        """
        Verifies that if a 1048 'Column cannot be null' error occurs,
        the method triggers _ensure_schema_compatibility and retries cleanly.
        """
        mock_data = pd.DataFrame([
            {
                "event_id": "EVT_TEST_1048",
                "sensor_id": "SNS_TRF_NAG_01",
                "segment_id": "SEG_NAG_01",
                "timestamp": pd.Timestamp("2026-10-13 16:00:00"),
                "vehicle_count": None,
                "avg_speed_kmh": 35.0,
                "free_flow_speed_kmh": 50.0,
                "current_travel_time_sec": 100,
                "free_flow_travel_time_sec": 100,
                "confidence_score": 0.9,
                "road_closure": False,
                "congestion_level": "LOW",
                "traffic_density_vpk": None,
                "source_type": "REAL_API",
                "road_name": "Ring Road",
            }
        ])

        # Raise 1048 on first call, succeed on second call
        attempt = [0]
        def mock_execute(query, params=None):
            if "ALTER TABLE" in query:
                return
            if attempt[0] == 0:
                attempt[0] += 1
                raise Exception("1048 (23000): Column 'avg_vehicle_count' cannot be null")
            return

        with patch.object(TrafficAnalytics, "load_traffic_dataframe", return_value=mock_data):
            with patch("analytics.traffic_analytics.get_db_cursor") as mock_cursor_ctx:
                mock_cursor = MagicMock()
                mock_cursor.execute.side_effect = mock_execute
                mock_cursor_ctx.return_value.__enter__.return_value = mock_cursor

                with patch.object(TrafficAnalytics, "_ensure_schema_compatibility") as mock_heal:
                    count = traffic_analytics.compute_and_store_hourly_metrics()
                    self.assertEqual(count, 1)
                    mock_heal.assert_called_once()

    def test_scheduled_batch_surfaces_rollup_error(self):
        """
        Verifies that when rollup aggregation fails, the batch orchestrator
        does NOT silently report SUCCESS; it logs the error, marks status PARTIAL,
        and includes the failure in the execution errors.
        """
        with patch("scripts.run_scheduled_batch.check_cadence_guard", return_value=(True, "OK")):
            with patch("scripts.run_scheduled_batch.get_db_cursor") as mock_cursor_ctx:
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = {"cnt": 10}
                mock_cursor_ctx.return_value.__enter__.return_value = mock_cursor

                with patch("ingestion.traffic.tomtom_client.tomtom_client.ingest_all_corridors", return_value={"successful": 15, "failed": 0}):
                    with patch("ingestion.weather.weather_client.weather_client.ingest_primary_city", return_value=True):
                        with patch("ingestion.air_quality.air_quality_client.air_quality_client.ingest_primary_city", return_value=True):
                            with patch("anomaly_detection.rule_engine.anomaly_engine.evaluate_operational_anomalies", return_value={"anomalies_detected": 0}):
                                with patch("analytics.traffic_analytics.traffic_analytics.compute_and_store_hourly_metrics", side_effect=Exception("1048 (23000): Column 'avg_vehicle_count' cannot be null")):
                                    with patch("analytics.environment_analytics.environment_analytics.compute_and_store_daily_metrics"):
                                        with patch("database.repository.repository.log_pipeline_run") as mock_log:
                                            res = run_live_scheduled_batch(force=True)

                                            self.assertIn("Rollup calculation error", str(res.get("errors")))
                                            self.assertEqual(res["status"], "PARTIAL")

                                            # Verify status passed to pipeline_runs is PARTIAL, not SUCCESS
                                            log_calls = [c for c in mock_log.call_args_list if c[1].get("status") in ("PARTIAL", "SUCCESS")]
                                            self.assertTrue(len(log_calls) > 0)
                                            self.assertEqual(log_calls[-1][1]["status"], "PARTIAL")

    def test_live_local_mysql_rollup_execution(self):
        """
        Verifies that compute_and_store_hourly_metrics runs cleanly against
        the actual local MySQL database without errors.
        """
        count = traffic_analytics.compute_and_store_hourly_metrics()
        self.assertIsInstance(count, int)
        self.assertGreater(count, 0)


if __name__ == "__main__":
    unittest.main()
