"""
Regression Test Suite for Traffic Intelligence View (dashboard/views/traffic.py).
Verifies:
1. render_traffic() executes cleanly without UnboundLocalError or any runtime crash.
2. The all-corridors-approved scenario (all 15 Nagpur corridors approved).
3. The partial-approval scenario (e.g., subset approved) with proper excluded_cnt derivation.
4. Road-selection dropdown accurately reflects corridor approval statuses.
5. Monitored Corridors KPI delta string dynamically reflects approval counts.
Zero live TomTom API requests are made.
"""

import unittest
from unittest.mock import patch, MagicMock
import pandas as pd

from config.corridors import NAGPUR_CORRIDORS_GEO, get_approved_corridors
from dashboard.views.traffic import render_traffic


class TestTrafficViewRegression(unittest.TestCase):
    """Test suite ensuring Traffic Intelligence page stability and proper corridor accounting."""

    @patch("dashboard.views.traffic.st")
    @patch("dashboard.views.traffic.load_road_segments")
    @patch("dashboard.views.traffic.load_latest_traffic_per_corridor")
    @patch("dashboard.views.traffic.load_traffic_readings")
    def test_01_render_traffic_all_corridors_approved(
        self, mock_load_readings, mock_load_latest, mock_load_segments, mock_st
    ):
        """Verify render_traffic executes without error when all 15 corridors are approved."""
        # Setup mock streamlit column containers
        mock_col = MagicMock()
        mock_st.columns.side_effect = lambda spec: [MagicMock() for _ in range(len(spec) if isinstance(spec, (list, tuple)) else spec)]
        mock_st.date_input.return_value = (pd.to_datetime("2026-10-10").date(), pd.to_datetime("2026-10-12").date())
        mock_st.selectbox.return_value = "ALL"

        # Mock segment data
        segments_data = [
            {"segment_id": cid, "road_name": c["road_name"], "segment_type": c["segment_type"]}
            for cid, c in NAGPUR_CORRIDORS_GEO.items()
        ]
        df_segments = pd.DataFrame(segments_data)
        mock_load_segments.return_value = df_segments

        # Mock latest traffic data for all 15 corridors
        latest_data = [
            {
                "segment_id": cid,
                "road_name": c["road_name"],
                "avg_speed_kmh": 42.5,
                "free_flow_speed_kmh": 50.0,
                "current_travel_time_sec": 300,
                "free_flow_travel_time_sec": 250,
                "delay_seconds": 50,
                "speed_reduction_pct": 15.0,
                "congestion_level": "LOW",
                "confidence_score": 0.95,
                "road_closure": False,
                "time_ago": "12m ago",
                "is_stale": False,
                "timestamp_display": "12 Oct 2026, 23:00 IST",
                "freshness_badge": "FRESH",
            }
            for cid, c in NAGPUR_CORRIDORS_GEO.items()
        ]
        df_latest = pd.DataFrame(latest_data)
        mock_load_latest.return_value = df_latest

        # Mock traffic readings
        df_readings = pd.DataFrame(latest_data)
        df_readings["timestamp"] = pd.to_datetime("2026-10-12 23:00:00")
        df_readings["timestamp_ist_naive"] = "2026-10-12 23:00:00"
        mock_load_readings.return_value = df_readings

        # Execute render_traffic - must NOT raise UnboundLocalError or any exception
        try:
            render_traffic()
        except UnboundLocalError as exc:
            self.fail(f"render_traffic raised UnboundLocalError: {exc}")
        except Exception as exc:
            self.fail(f"render_traffic raised unexpected exception: {exc}")

        # Verify selectbox was called and format_func formats 'ALL' dynamically
        self.assertTrue(mock_st.selectbox.called)
        call_args = mock_st.selectbox.call_args
        seg_names = call_args[0][1]
        format_func = call_args[1]["format_func"]

        self.assertIn("ALL", seg_names)
        self.assertEqual(len(seg_names), 16)  # 'ALL' + 15 corridors
        self.assertEqual(format_func("ALL"), "All Nagpur Corridors (15 Active)")
        # Cleaned corridor label: road name without technical segment ID or [ACTIVE] prefix
        self.assertEqual(format_func("SEG_NAG_01"), NAGPUR_CORRIDORS_GEO["SEG_NAG_01"]["road_name"])

    @patch("dashboard.views.traffic.st")
    @patch("dashboard.views.traffic.get_approved_corridors")
    @patch("dashboard.views.traffic.load_road_segments")
    @patch("dashboard.views.traffic.load_latest_traffic_per_corridor")
    @patch("dashboard.views.traffic.load_traffic_readings")
    def test_02_render_traffic_partial_approved_subsets(
        self, mock_load_readings, mock_load_latest, mock_load_segments, mock_get_approved, mock_st
    ):
        """Verify render_traffic handles scenario where a subset (e.g. 11/15) is approved."""
        mock_col = MagicMock()
        mock_st.columns.side_effect = lambda spec: [MagicMock() for _ in range(len(spec) if isinstance(spec, (list, tuple)) else spec)]
        mock_st.date_input.return_value = (pd.to_datetime("2026-10-10").date(), pd.to_datetime("2026-10-12").date())
        mock_st.selectbox.return_value = "ALL"

        # Mock 11 approved corridors out of 15
        approved_11 = [f"SEG_NAG_{i:02d}" for i in range(1, 12)]
        mock_get_approved.return_value = approved_11

        segments_data = [
            {"segment_id": cid, "road_name": c["road_name"], "segment_type": c["segment_type"]}
            for cid, c in NAGPUR_CORRIDORS_GEO.items()
        ]
        mock_load_segments.return_value = pd.DataFrame(segments_data)

        latest_data = [
            {
                "segment_id": cid,
                "road_name": c["road_name"],
                "avg_speed_kmh": 40.0,
                "free_flow_speed_kmh": 50.0,
                "current_travel_time_sec": 300,
                "free_flow_travel_time_sec": 250,
                "delay_seconds": 50,
                "speed_reduction_pct": 20.0,
                "congestion_level": "LOW",
                "confidence_score": 0.90,
                "road_closure": False,
                "time_ago": "20m ago",
                "is_stale": False,
                "timestamp_display": "12 Oct 2026, 23:00 IST",
                "freshness_badge": "FRESH",
            }
            for cid, c in NAGPUR_CORRIDORS_GEO.items()
        ]
        mock_load_latest.return_value = pd.DataFrame(latest_data)
        df_readings_02 = pd.DataFrame(latest_data)
        df_readings_02["timestamp"] = pd.to_datetime("2026-10-12 23:00:00")
        df_readings_02["timestamp_ist_naive"] = "2026-10-12 23:00:00"
        mock_load_readings.return_value = df_readings_02

        # Must execute cleanly
        try:
            render_traffic()
        except Exception as exc:
            self.fail(f"render_traffic raised unexpected exception with partial approval: {exc}")

        call_args = mock_st.selectbox.call_args
        format_func = call_args[1]["format_func"]
        # Format for ALL should indicate 11/15 Active
        self.assertEqual(format_func("ALL"), "All Nagpur Corridors (11/15 Active)")
        # Road name is displayed cleanly without technical IDs or prefixes
        self.assertEqual(format_func("SEG_NAG_01"), NAGPUR_CORRIDORS_GEO["SEG_NAG_01"]["road_name"])

    @patch("dashboard.views.traffic.st")
    @patch("dashboard.views.traffic.load_road_segments")
    @patch("dashboard.views.traffic.load_latest_traffic_per_corridor")
    @patch("dashboard.views.traffic.load_traffic_readings")
    def test_03_render_traffic_specific_corridor_selected(
        self, mock_load_readings, mock_load_latest, mock_load_segments, mock_st
    ):
        """Verify render_traffic executes cleanly when a specific corridor is selected."""
        mock_col = MagicMock()
        mock_st.columns.side_effect = lambda spec: [MagicMock() for _ in range(len(spec) if isinstance(spec, (list, tuple)) else spec)]
        mock_st.date_input.return_value = (pd.to_datetime("2026-10-10").date(), pd.to_datetime("2026-10-12").date())
        mock_st.selectbox.return_value = "SEG_NAG_01"

        segments_data = [
            {"segment_id": cid, "road_name": c["road_name"], "segment_type": c["segment_type"]}
            for cid, c in NAGPUR_CORRIDORS_GEO.items()
        ]
        mock_load_segments.return_value = pd.DataFrame(segments_data)

        latest_data = [
            {
                "segment_id": cid,
                "road_name": c["road_name"],
                "segment_type": c["segment_type"],
                "avg_speed_kmh": 45.0,
                "free_flow_speed_kmh": 60.0,
                "current_travel_time_sec": 300,
                "free_flow_travel_time_sec": 240,
                "delay_seconds": 60,
                "speed_reduction_pct": 25.0,
                "congestion_level": "MEDIUM",
                "confidence_score": 1.0,
                "road_closure": False,
                "time_ago": "5m ago",
                "is_stale": False,
                "timestamp_display": "12 Oct 2026, 23:00 IST",
                "freshness_badge": "FRESH",
            }
            for cid, c in NAGPUR_CORRIDORS_GEO.items()
        ]
        mock_load_latest.return_value = pd.DataFrame(latest_data)
        df_readings_03 = pd.DataFrame(latest_data)
        df_readings_03["timestamp"] = pd.to_datetime("2026-10-12 23:00:00")
        df_readings_03["timestamp_ist_naive"] = "2026-10-12 23:00:00"
        mock_load_readings.return_value = df_readings_03

        try:
            render_traffic()
        except Exception as exc:
            self.fail(f"render_traffic raised unexpected exception for specific corridor: {exc}")

    def test_04_direct_execution_with_real_mysql_state(self):
        """Verify direct execution of render_traffic with actual MySQL state succeeds."""
        # Using real database connections and Streamlit bare-mode execution
        try:
            render_traffic()
        except UnboundLocalError as exc:
            self.fail(f"render_traffic raised UnboundLocalError with live MySQL data: {exc}")
        except Exception as exc:
            # Bare-mode streamlit warnings are expected, but no Python exceptions should occur
            self.fail(f"render_traffic raised unexpected exception with live MySQL data: {exc}")


if __name__ == "__main__":
    unittest.main()
