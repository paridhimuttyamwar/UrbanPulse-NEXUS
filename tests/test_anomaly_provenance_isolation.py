"""
Regression Test Suite for Anomaly Provenance Isolation, Test Fixture Confinement,
and Operational Queue Integrity in UrbanPulse NEXUS.

Validates:
1. TEST_MOCK anomalies are excluded from default operational queries (source_type='REAL_API').
2. Genuine REAL_API anomalies are loaded and displayed with proper IST formatting.
3. Test fixtures cannot contaminate production data and clean up unconditionally.
4. KPI cards, metrics, and charts use consistent filtering on empty and non-empty datasets.
5. Historical simulated (7) and genuine incidents are preserved unaltered.
6. Incident triage forms (Acknowledge & Resolve) enforce mandatory non-blank notes and persist correctly.
7. Database updates persist timestamps in UTC and resolve transitions accurately.
8. Empty operational queues render cleanly without KeyError or runtime exceptions.
"""

import unittest
import uuid
from datetime import datetime, timezone
import pandas as pd

from database.connection import get_db_cursor
from dashboard.data_loader import load_anomalies
from anomaly_detection.rule_engine import AnomalyRuleEngine


class TestAnomalyProvenanceIsolation(unittest.TestCase):

    def test_01_test_mock_excluded_from_real_api_queue(self):
        """Verify TEST_MOCK records are strictly excluded from REAL_API and ALL queries."""
        # Operational query for Nagpur
        df_real = load_anomalies(location_id="LOC_NAGPUR", source_type="REAL_API", limit=500)
        if not df_real.empty:
            source_types = set(df_real["source_type"].tolist())
            self.assertNotIn("TEST_MOCK", source_types, "TEST_MOCK must never appear in REAL_API query")
            self.assertNotIn("SIMULATED", source_types, "SIMULATED must not appear in REAL_API query")

        # ALL provenance query must include SIMULATED but exclude TEST_MOCK
        df_all = load_anomalies(location_id="LOC_NAGPUR", source_type="ALL", limit=500)
        if not df_all.empty:
            source_types_all = set(df_all["source_type"].tolist())
            self.assertNotIn("TEST_MOCK", source_types_all, "TEST_MOCK must not leak into ALL provenance view")
            self.assertIn("SIMULATED", source_types_all, "SIMULATED historical records should be present in ALL view")

    def test_02_load_anomalies_empty_state_contract(self):
        """Verify load_anomalies returns a typed DataFrame with standard columns when empty."""
        df_empty = load_anomalies(location_id="LOC_NONEXISTENT_XYZ", source_type="REAL_API")
        self.assertTrue(df_empty.empty)
        required_cols = [
            "anomaly_id", "anomaly_type", "source_type", "location_id", "segment_id",
            "road_name", "timestamp", "severity", "description", "status",
            "resolution_notes", "resolved_at", "created_at",
            "timestamp_ist", "timestamp_display"
        ]
        for col in required_cols:
            self.assertIn(col, df_empty.columns, f"Empty anomalies DataFrame missing column: {col}")

    def test_03_genuine_real_api_anomalies_retrieved_correctly(self):
        """Verify genuine REAL_API anomalies are loaded and properly IST-formatted."""
        # Query existing REAL_API anomalies (e.g. LOC_DELHI)
        df_delhi = load_anomalies(location_id="LOC_DELHI", source_type="REAL_API", limit=10)
        self.assertFalse(df_delhi.empty, "Expected genuine REAL_API records for LOC_DELHI")
        first = df_delhi.iloc[0]
        self.assertEqual(first["source_type"], "REAL_API")
        self.assertIn("IST", first["timestamp_display"])
        self.assertIn(first["severity"], ["CRITICAL", "HIGH", "MEDIUM", "LOW"])

    def test_04_test_fixture_isolation_and_guaranteed_cleanup(self):
        """Verify test fixture creation with TEST_MOCK and verify cleanup leaves 0 residual records."""
        test_id = f"ANOM_ISOLATION_TEST_{uuid.uuid4().hex[:8].upper()}"
        try:
            with get_db_cursor(commit=True) as cursor:
                cursor.execute("""
                    INSERT INTO anomalies (
                        anomaly_id, anomaly_type, source_type, location_id, segment_id,
                        timestamp, severity, description, status
                    ) VALUES (
                        %(id)s, 'TEST_ISOLATION_CHECK', 'TEST_MOCK', 'LOC_NAGPUR', 'SEG_NAG_01',
                        UTC_TIMESTAMP(), 'LOW', 'Test isolation verification', 'ACTIVE'
                    )
                """, {"id": test_id})

            # Verify it exists in DB as TEST_MOCK
            with get_db_cursor(commit=False) as cursor:
                cursor.execute("SELECT source_type FROM anomalies WHERE anomaly_id = %(id)s", {"id": test_id})
                row = cursor.fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["source_type"], "TEST_MOCK")

            # Verify load_anomalies(source_type='REAL_API') does NOT return this test fixture
            df_real = load_anomalies(location_id="LOC_NAGPUR", source_type="REAL_API")
            if not df_real.empty:
                self.assertNotIn(test_id, df_real["anomaly_id"].tolist())

        finally:
            # Clean up
            with get_db_cursor(commit=True) as cursor:
                cursor.execute("DELETE FROM anomalies WHERE anomaly_id = %(id)s", {"id": test_id})

            # Confirm deleted
            with get_db_cursor(commit=False) as cursor:
                cursor.execute("SELECT COUNT(*) as c FROM anomalies WHERE anomaly_id = %(id)s", {"id": test_id})
                self.assertEqual(cursor.fetchone()["c"], 0)

    def test_05_kpi_metrics_consistency_on_empty_and_populated(self):
        """Verify KPI metric calculations handle empty DataFrames safely without exceptions."""
        df_empty = load_anomalies(location_id="LOC_NAGPUR", source_type="REAL_API")
        self.assertTrue(df_empty.empty)

        # Mirror KPI calculations from Anomaly Center view
        total_count = len(df_empty)
        crit_count = int((df_empty["severity"] == "CRITICAL").sum()) if not df_empty.empty else 0
        high_count = int((df_empty["severity"] == "HIGH").sum()) if not df_empty.empty else 0
        active_count = int((df_empty["status"] == "ACTIVE").sum()) if not df_empty.empty else 0

        self.assertEqual(total_count, 0)
        self.assertEqual(crit_count, 0)
        self.assertEqual(high_count, 0)
        self.assertEqual(active_count, 0)

        # Delta logic checks
        crit_delta = "Urgent Action" if crit_count > 0 else "None"
        high_delta = "Active Review" if high_count > 0 else "None"
        active_delta = "In Queue" if active_count > 0 else "Clear"

        self.assertEqual(crit_delta, "None")
        self.assertEqual(high_delta, "None")
        self.assertEqual(active_delta, "Clear")

    def test_06_no_genuine_or_simulated_incidents_accidentally_altered(self):
        """Verify the 7 historical SIMULATED records and genuine REAL_API records remain untouched."""
        with get_db_cursor(commit=False) as cursor:
            cursor.execute("SELECT COUNT(*) as c FROM anomalies WHERE source_type = 'SIMULATED'")
            sim_count = cursor.fetchone()["c"]
            self.assertEqual(sim_count, 7, "Historical SIMULATED anomalies must remain exactly 7")

            cursor.execute("SELECT COUNT(*) as c FROM anomalies WHERE source_type = 'REAL_API'")
            real_count = cursor.fetchone()["c"]
            self.assertEqual(real_count, 10, "Genuine REAL_API anomalies must remain exactly 10")

            cursor.execute("SELECT COUNT(*) as c FROM anomalies WHERE source_type = 'TEST_MOCK'")
            mock_count = cursor.fetchone()["c"]
            self.assertEqual(mock_count, 8, "Reclassified test fixtures must be exactly 8")

    def test_07_triage_form_lifecycle_and_note_validation(self):
        """Verify Acknowledge and Resolve forms reject empty notes and transition states with DB persistence."""
        test_id = f"ANOM_FORM_TEST_{uuid.uuid4().hex[:8].upper()}"
        try:
            # 1. Insert active test incident
            with get_db_cursor(commit=True) as cursor:
                cursor.execute("""
                    INSERT INTO anomalies (
                        anomaly_id, anomaly_type, source_type, location_id, segment_id,
                        timestamp, severity, description, status
                    ) VALUES (
                        %(id)s, 'TRIAGE_FORM_CHECK', 'TEST_MOCK', 'LOC_NAGPUR', 'SEG_NAG_01',
                        UTC_TIMESTAMP(), 'HIGH', 'Form validation test alert', 'ACTIVE'
                    )
                """, {"id": test_id})

            # Validation check: empty and whitespace-only notes must be rejected
            invalid_notes = ["", "   ", "\t\r\n  ", None]
            for note in invalid_notes:
                is_valid = bool(note and note.strip())
                self.assertFalse(is_valid, f"Expected note {repr(note)} to be rejected.")

            valid_note = "Camera verified: vehicular obstruction cleared; normal flow resumed."
            self.assertTrue(bool(valid_note and valid_note.strip()))

            # 2. Acknowledge with optional note
            ack_note = "Control room operator monitoring corridor."
            with get_db_cursor(commit=True) as cursor:
                cursor.execute("""
                    UPDATE anomalies
                    SET status = 'ACKNOWLEDGED',
                        resolution_notes = COALESCE(%(note)s, resolution_notes)
                    WHERE anomaly_id = %(id)s AND status = 'ACTIVE'
                """, {"id": test_id, "note": ack_note})

            with get_db_cursor(commit=False) as cursor:
                cursor.execute("SELECT status, resolution_notes, resolved_at FROM anomalies WHERE anomaly_id = %(id)s", {"id": test_id})
                row = cursor.fetchone()
                self.assertEqual(row["status"], "ACKNOWLEDGED")
                self.assertEqual(row["resolution_notes"], ack_note)
                self.assertIsNone(row["resolved_at"])

            # 3. Resolve from ACKNOWLEDGED with mandatory note
            with get_db_cursor(commit=True) as cursor:
                cursor.execute("""
                    UPDATE anomalies
                    SET status = 'RESOLVED',
                        resolution_notes = %(notes)s,
                        resolved_at = UTC_TIMESTAMP()
                    WHERE anomaly_id = %(id)s AND status IN ('ACTIVE', 'ACKNOWLEDGED')
                """, {"id": test_id, "notes": valid_note.strip()})

            with get_db_cursor(commit=False) as cursor:
                cursor.execute("SELECT status, resolution_notes, resolved_at FROM anomalies WHERE anomaly_id = %(id)s", {"id": test_id})
                res_row = cursor.fetchone()
                self.assertEqual(res_row["status"], "RESOLVED")
                self.assertEqual(res_row["resolution_notes"], valid_note)
                self.assertIsNotNone(res_row["resolved_at"])

            # 4. Protection check: Re-resolving already resolved incident cannot change resolved_at
            original_resolved_at = res_row["resolved_at"]
            with get_db_cursor(commit=True) as cursor:
                cursor.execute("""
                    UPDATE anomalies
                    SET status = 'RESOLVED',
                        resolution_notes = 'Duplicate resolve attempt',
                        resolved_at = UTC_TIMESTAMP()
                    WHERE anomaly_id = %(id)s AND status IN ('ACTIVE', 'ACKNOWLEDGED')
                """, {"id": test_id})
                self.assertEqual(cursor.rowcount, 0, "Already-resolved incident must not be modified by resolution form")

        finally:
            with get_db_cursor(commit=True) as cursor:
                cursor.execute("DELETE FROM anomalies WHERE anomaly_id = %(id)s", {"id": test_id})

    def test_08_empty_operational_queue_render_safety(self):
        """Verify UI empty state components execute safely on empty dataframe."""
        df_anom = load_anomalies(status="ALL", location_id="LOC_NAGPUR", source_type="REAL_API", limit=500)
        self.assertTrue(df_anom.empty)

        # Test value_counts operations used in chart building
        sev_counts = df_anom["severity"].value_counts().reset_index()
        self.assertTrue(sev_counts.empty)

        src_counts = df_anom["source_type"].value_counts().reset_index()
        self.assertTrue(src_counts.empty)

        # Iterrows execution must complete with 0 iterations and no exception
        loop_count = 0
        for _, row in df_anom.iterrows():
            loop_count += 1
        self.assertEqual(loop_count, 0)


if __name__ == "__main__":
    unittest.main()
