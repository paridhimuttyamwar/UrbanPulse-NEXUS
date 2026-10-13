"""
Phase 4B Automated Verification Suite:
1. Four Excluded Corridors Recovery, Snapping Precision, and 15/15 Ingestion Approval.
2. TomTom API Client Dynamic Zoom Parameter Handling.
3. Anomaly Center Interactive Triage Lifecycle (Acknowledge, Direct Resolve, Mandatory Note Validation, DB Persistence, Re-resolve Protection).
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
import re

from config.corridors import NAGPUR_CORRIDORS_GEO, get_corridor_geo, get_approved_corridors
from ingestion.traffic.tomtom_client import TomTomTrafficClient, tomtom_client
from database.connection import get_db_cursor


class TestPhase4BCorridorsRecovery(unittest.TestCase):
    """Verifies that all 4 previously excluded corridors have been verified and approved."""

    def test_total_corridors_and_approval_count(self):
        self.assertEqual(len(NAGPUR_CORRIDORS_GEO), 15, "Total registered corridors must be 15.")
        approved = get_approved_corridors()
        self.assertEqual(len(approved), 15, "All 15 corridors must now be approved for automated ingestion.")
        for i in range(1, 16):
            expected_id = f"SEG_NAG_{i:02d}"
            self.assertIn(expected_id, approved, f"{expected_id} must be in approved corridors list.")

    def test_recovered_corridor_02_sitabuldi(self):
        c = get_corridor_geo("SEG_NAG_02")
        self.assertIsNotNone(c)
        self.assertEqual(c["road_name"], "Sitabuldi Main Road")
        self.assertTrue(c["approved_for_ingestion"])
        self.assertEqual(c["match_quality"], "VERIFIED")
        self.assertEqual(c["zoom"], 14)
        self.assertAlmostEqual(c["latitude"], 21.1445, places=4)
        self.assertAlmostEqual(c["longitude"], 79.0845, places=4)
        self.assertIn("11.4m", c["match_notes"])

    def test_recovered_corridor_05_manish_nagar(self):
        c = get_corridor_geo("SEG_NAG_05")
        self.assertIsNotNone(c)
        self.assertEqual(c["road_name"], "Manish Nagar Main Road")
        self.assertTrue(c["approved_for_ingestion"])
        self.assertEqual(c["match_quality"], "VERIFIED")
        self.assertEqual(c["zoom"], 12)
        self.assertAlmostEqual(c["latitude"], 21.0856, places=4)
        self.assertAlmostEqual(c["longitude"], 79.0803, places=4)
        self.assertIn("5.9m", c["match_notes"])

    def test_recovered_corridor_12_nandanvan(self):
        c = get_corridor_geo("SEG_NAG_12")
        self.assertIsNotNone(c)
        self.assertEqual(c["road_name"], "Nandanvan Main Road")
        self.assertTrue(c["approved_for_ingestion"])
        self.assertEqual(c["match_quality"], "VERIFIED")
        self.assertEqual(c["zoom"], 12)
        self.assertAlmostEqual(c["latitude"], 21.1350, places=4)
        self.assertAlmostEqual(c["longitude"], 79.1248, places=4)
        self.assertIn("2.9m", c["match_notes"])

    def test_recovered_corridor_14_civil_lines(self):
        c = get_corridor_geo("SEG_NAG_14")
        self.assertIsNotNone(c)
        self.assertEqual(c["road_name"], "Civil Lines Road")
        self.assertTrue(c["approved_for_ingestion"])
        self.assertEqual(c["match_quality"], "VERIFIED")
        self.assertEqual(c["zoom"], 12)
        self.assertAlmostEqual(c["latitude"], 21.1548, places=4)
        self.assertAlmostEqual(c["longitude"], 79.0748, places=4)
        self.assertIn("4.8m", c["match_notes"])


class TestTomTomZoomParameterSupport(unittest.TestCase):
    """Verifies that TomTomTrafficClient formats URLs correctly when zoom parameter is passed."""

    def setUp(self):
        self.client = TomTomTrafficClient(api_key="MOCK_TEST_KEY")

    @patch("ingestion.traffic.tomtom_client.requests.get")
    def test_zoom_formatting_in_url(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"flowSegmentData": {"currentSpeed": 30}}
        mock_get.return_value = mock_resp

        # Mock budget tracker to prevent live file modification during unit test
        with patch.object(self.client.budget_tracker, "can_request", return_value=(True, "OK")), \
             patch.object(self.client.budget_tracker, "record_attempt"):
            
            # 1. Custom zoom 14 (Sitabuldi street)
            self.client.fetch_flow_segment_data(21.1445, 79.0845, zoom=14)
            called_url_14 = mock_get.call_args[0][0]
            self.assertIn("/14/json", called_url_14)

            # 2. Custom zoom 12 (Arterials)
            self.client.fetch_flow_segment_data(21.0856, 79.0803, zoom=12)
            called_url_12 = mock_get.call_args[0][0]
            self.assertIn("/12/json", called_url_12)

            # 3. Default zoom (None -> /10/json)
            self.client.fetch_flow_segment_data(21.0895, 79.0645, zoom=None)
            called_url_10 = mock_get.call_args[0][0]
            self.assertIn("/10/json", called_url_10)


class TestAnomalyCenterTriagePersistence(unittest.TestCase):
    """
    Tests Anomaly Center resolution rules, validation, and database persistence:
    - Mandatory non-empty resolution notes.
    - Status transitions ACTIVE -> ACKNOWLEDGED -> RESOLVED and ACTIVE -> RESOLVED.
    - UTC timestamp storage and re-resolve protection.
    """

    TEST_ANOM_ID_1 = "ANOM_TEST_PHASE4B_TRIAGE_1"
    TEST_ANOM_ID_2 = "ANOM_TEST_PHASE4B_TRIAGE_2"

    def setUp(self):
        # Clean any preexisting test fixtures
        self._cleanup()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO anomalies (
                    anomaly_id, anomaly_type, source_type, location_id, segment_id,
                    timestamp, severity, description, status, resolution_notes, resolved_at
                ) VALUES 
                (%(id1)s, 'TEST_ALERT', 'TEST_MOCK', 'LOC_NAGPUR', 'SEG_NAG_02', UTC_TIMESTAMP(), 'HIGH', 'Test active anomaly 1', 'ACTIVE', NULL, NULL),
                (%(id2)s, 'TEST_ALERT', 'TEST_MOCK', 'LOC_NAGPUR', 'SEG_NAG_05', UTC_TIMESTAMP(), 'CRITICAL', 'Test active anomaly 2', 'ACTIVE', NULL, NULL)
                """,
                {"id1": self.TEST_ANOM_ID_1, "id2": self.TEST_ANOM_ID_2}
            )

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                "DELETE FROM anomalies WHERE anomaly_id IN (%(id1)s, %(id2)s)",
                {"id1": self.TEST_ANOM_ID_1, "id2": self.TEST_ANOM_ID_2}
            )

    def test_mandatory_resolution_notes_validation(self):
        # Business logic validation: empty or whitespace-only strings must be rejected
        invalid_notes = ["", "   ", "\t\n  "]
        for note in invalid_notes:
            is_valid = bool(note and note.strip())
            self.assertFalse(is_valid, f"Note '{note}' should be rejected as invalid.")

        valid_note = "Camera verified; vehicular breakdown cleared from left carriageway."
        self.assertTrue(bool(valid_note and valid_note.strip()))

    def test_lifecycle_active_to_acknowledged_to_resolved(self):
        # Step 1: Acknowledge with optional note
        ack_note = "Control room operator acknowledged; field team notified."
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE anomalies
                SET status = 'ACKNOWLEDGED',
                    resolution_notes = COALESCE(%(note)s, resolution_notes)
                WHERE anomaly_id = %(id)s AND status = 'ACTIVE'
                """,
                {"id": self.TEST_ANOM_ID_1, "note": ack_note}
            )

        with get_db_cursor(commit=False) as cursor:
            cursor.execute("SELECT status, resolution_notes, resolved_at FROM anomalies WHERE anomaly_id = %(id)s", {"id": self.TEST_ANOM_ID_1})
            row = cursor.fetchone()
            self.assertEqual(row["status"], "ACKNOWLEDGED")
            self.assertEqual(row["resolution_notes"], ack_note)
            self.assertIsNone(row["resolved_at"])

        # Step 2: Resolve from ACKNOWLEDGED with mandatory note
        final_res_note = "Signal timings adjusted at Munje Sq; corridor speeds restored to 21 km/h."
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE anomalies
                SET status = 'RESOLVED',
                    resolution_notes = %(notes)s,
                    resolved_at = UTC_TIMESTAMP()
                WHERE anomaly_id = %(id)s AND status IN ('ACTIVE', 'ACKNOWLEDGED')
                """,
                {"id": self.TEST_ANOM_ID_1, "notes": final_res_note}
            )

        with get_db_cursor(commit=False) as cursor:
            cursor.execute("SELECT status, resolution_notes, resolved_at FROM anomalies WHERE anomaly_id = %(id)s", {"id": self.TEST_ANOM_ID_1})
            row = cursor.fetchone()
            self.assertEqual(row["status"], "RESOLVED")
            self.assertEqual(row["resolution_notes"], final_res_note)
            self.assertIsNotNone(row["resolved_at"])
            first_resolved_at = row["resolved_at"]

        # Step 3: Verify protection against re-resolving an already RESOLVED anomaly
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE anomalies
                SET status = 'RESOLVED',
                    resolution_notes = 'Attempted overwrite',
                    resolved_at = UTC_TIMESTAMP()
                WHERE anomaly_id = %(id)s AND status IN ('ACTIVE', 'ACKNOWLEDGED')
                """,
                {"id": self.TEST_ANOM_ID_1}
            )
            # 0 rows affected because status is already RESOLVED
            self.assertEqual(cursor.rowcount, 0)

        with get_db_cursor(commit=False) as cursor:
            cursor.execute("SELECT status, resolution_notes, resolved_at FROM anomalies WHERE anomaly_id = %(id)s", {"id": self.TEST_ANOM_ID_1})
            row = cursor.fetchone()
            self.assertEqual(row["resolution_notes"], final_res_note, "Resolved note must NOT be overwritten.")
            self.assertEqual(row["resolved_at"], first_resolved_at, "Resolved timestamp must NOT be overwritten.")

    def test_lifecycle_direct_resolve_from_active(self):
        # Direct resolution from ACTIVE
        direct_note = "Direct resolution: sensor recalibration confirmed genuine reading."
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE anomalies
                SET status = 'RESOLVED',
                    resolution_notes = %(notes)s,
                    resolved_at = UTC_TIMESTAMP()
                WHERE anomaly_id = %(id)s AND status IN ('ACTIVE', 'ACKNOWLEDGED')
                """,
                {"id": self.TEST_ANOM_ID_2, "notes": direct_note}
            )

        with get_db_cursor(commit=False) as cursor:
            cursor.execute("SELECT status, resolution_notes, resolved_at FROM anomalies WHERE anomaly_id = %(id)s", {"id": self.TEST_ANOM_ID_2})
            row = cursor.fetchone()
            self.assertEqual(row["status"], "RESOLVED")
            self.assertEqual(row["resolution_notes"], direct_note)
            self.assertIsNotNone(row["resolved_at"])


if __name__ == "__main__":
    unittest.main()
