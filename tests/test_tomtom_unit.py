"""
Unit tests for TomTom Traffic Client parsing, normalization, and validation.
Uses simulated mock API payloads to verify business logic without consuming live API quota.
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from ingestion.traffic.tomtom_client import TomTomTrafficClient


class TestTomTomTrafficClient(unittest.TestCase):
    def setUp(self):
        self.client = TomTomTrafficClient(api_key="TEST_MOCK_KEY_12345")

    def test_calculate_congestion_level(self):
        # >= 75% -> LOW
        self.assertEqual(self.client.calculate_congestion_level(65.0, 70.0), "LOW")
        # 50% - 74% -> MEDIUM
        self.assertEqual(self.client.calculate_congestion_level(40.0, 70.0), "MEDIUM")
        # 30% - 49% -> HIGH
        self.assertEqual(self.client.calculate_congestion_level(25.0, 70.0), "HIGH")
        # < 30% -> SEVERE
        self.assertEqual(self.client.calculate_congestion_level(15.0, 70.0), "SEVERE")

    def test_normalize_flow_response_preserves_genuine_metrics(self):
        mock_payload = {
            "flowSegmentData": {
                "frc": "FRC2",
                "currentSpeed": 52,
                "freeFlowSpeed": 68,
                "currentTravelTime": 415,
                "freeFlowTravelTime": 317,
                "confidence": 0.89,
                "roadClosure": False,
                "coordinates": {"coordinate": [{"latitude": 21.0895, "longitude": 79.0645}]}
            }
        }

        ok, norm, err = self.client.normalize_flow_response(mock_payload, "SEG_NAG_01")
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertEqual(norm["segment_id"], "SEG_NAG_01")
        self.assertEqual(norm["sensor_id"], "SNS_TRF_NAG_01")
        self.assertEqual(norm["avg_speed_kmh"], 52.0)
        self.assertEqual(norm["free_flow_speed_kmh"], 68.0)
        self.assertEqual(norm["current_travel_time_sec"], 415)
        self.assertEqual(norm["free_flow_travel_time_sec"], 317)
        self.assertEqual(norm["confidence_score"], 0.89)
        self.assertEqual(norm["road_closure"], False)
        self.assertEqual(norm["source_type"], "REAL_API")
        
        # Mandatory: Unmeasured attributes MUST be None
        self.assertIsNone(norm["vehicle_count"])
        self.assertIsNone(norm["traffic_density_vpk"])

    def test_missing_flow_segment_data_fails_gracefully(self):
        mock_payload = {"error": "Invalid point"}
        ok, norm, err = self.client.normalize_flow_response(mock_payload, "SEG_NAG_01")
        self.assertFalse(ok)
        self.assertIsNone(norm)
        self.assertIn("flowSegmentData", err)

    def test_missing_current_speed_fails_gracefully(self):
        mock_payload = {
            "flowSegmentData": {
                "freeFlowSpeed": 60,
                # Missing currentSpeed
            }
        }
        ok, norm, err = self.client.normalize_flow_response(mock_payload, "SEG_NAG_01")
        self.assertFalse(ok)
        self.assertIsNone(norm)
        self.assertIn("currentSpeed", err)


if __name__ == "__main__":
    unittest.main()
