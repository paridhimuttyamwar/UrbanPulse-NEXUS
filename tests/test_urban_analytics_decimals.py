"""
Unit and Regression Tests for Urban Analytics MySQL Decimal/Float Compatibility.
Tests that numeric columns returned as decimal.Decimal from MySQL drivers
are safely converted to float/numeric dtypes and do not raise TypeErrors during arithmetic.
"""

import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

from analytics.traffic_analytics import traffic_analytics
from dashboard.views.urban_analytics import render_urban_analytics
from dashboard.data_loader import load_road_segments, load_traffic_readings


class TestUrbanAnalyticsDecimalHandling(unittest.TestCase):
    """Verifies that decimal.Decimal objects from MySQL do not cause TypeErrors during arithmetic."""

    def test_load_traffic_dataframe_converts_decimals_to_numeric(self):
        """Verify traffic_analytics.load_traffic_dataframe coerces Decimal objects to float."""
        mock_row = {
            "event_id": "EVT_TEST_DECIMAL_01",
            "sensor_id": "SNS_TRF_NAG_01",
            "segment_id": "SEG_NAG_01",
            "timestamp": "2026-10-12 12:00:00",
            "vehicle_count": 42,
            "avg_speed_kmh": Decimal("32.50"),
            "free_flow_speed_kmh": Decimal("50.00"),
            "current_travel_time_sec": 300,
            "free_flow_travel_time_sec": 200,
            "confidence_score": Decimal("0.950"),
            "road_closure": 0,
            "congestion_level": "LOW",
            "traffic_density_vpk": Decimal("15.20"),
            "source_type": "REAL_API",
        }

        with patch("analytics.traffic_analytics.get_db_cursor") as mock_cursor_ctx:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [mock_row]
            mock_cursor_ctx.return_value.__enter__.return_value = mock_cursor

            df = traffic_analytics.load_traffic_dataframe(limit=10)

            self.assertFalse(df.empty)
            self.assertEqual(df["avg_speed_kmh"].dtype, np.float64)
            self.assertEqual(df["free_flow_speed_kmh"].dtype, np.float64)
            self.assertEqual(df["confidence_score"].dtype, np.float64)
            self.assertEqual(df["traffic_density_vpk"].dtype, np.float64)

            # Division must succeed without TypeError
            speed_ratio = df["avg_speed_kmh"] / df["free_flow_speed_kmh"]
            self.assertAlmostEqual(float(speed_ratio.iloc[0]), 32.5 / 50.0, places=4)

    def test_speed_reduction_calculation_with_decimal_and_edge_cases(self):
        """
        Verify speed reduction calculation handles:
        - Actual decimal.Decimal values
        - Mixed float and Decimal values
        - Zero denominators (free_flow_speed == 0)
        - None / NaN missing values
        - Speeds faster than free-flow (clamped to 0.0%)
        """
        raw_data = [
            # Standard reduction: 30 / 60 -> 50%
            {"avg_speed_kmh": Decimal("30.00"), "free_flow_speed_kmh": Decimal("60.00")},
            # Mixed float and Decimal: 40.0 / Decimal(50.0) -> 20%
            {"avg_speed_kmh": 40.0, "free_flow_speed_kmh": Decimal("50.00")},
            # Faster than free-flow: 65.0 / 60.0 -> 0.0%
            {"avg_speed_kmh": Decimal("65.00"), "free_flow_speed_kmh": Decimal("60.00")},
            # Zero free-flow denominator: should return 0.0%, no ZeroDivisionError
            {"avg_speed_kmh": Decimal("25.00"), "free_flow_speed_kmh": Decimal("0.00")},
            # None / NULL values: should return 0.0%
            {"avg_speed_kmh": None, "free_flow_speed_kmh": Decimal("50.00")},
            {"avg_speed_kmh": Decimal("30.00"), "free_flow_speed_kmh": None},
        ]
        df = pd.DataFrame(raw_data)

        # Convert columns as done in views and loaders
        for col in ["avg_speed_kmh", "free_flow_speed_kmh"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        def _calc_speed_red(row):
            spd = row.get("avg_speed_kmh")
            ff = row.get("free_flow_speed_kmh")
            if pd.notna(spd) and pd.notna(ff) and ff > 0:
                try:
                    return max(0.0, (1.0 - (float(spd) / float(ff))) * 100.0)
                except (ZeroDivisionError, TypeError, ValueError):
                    return 0.0
            return 0.0

        reductions = df.apply(_calc_speed_red, axis=1).tolist()

        self.assertAlmostEqual(reductions[0], 50.0, places=2)
        self.assertAlmostEqual(reductions[1], 20.0, places=2)
        self.assertAlmostEqual(reductions[2], 0.0, places=2)
        self.assertAlmostEqual(reductions[3], 0.0, places=2)
        self.assertAlmostEqual(reductions[4], 0.0, places=2)
        self.assertAlmostEqual(reductions[5], 0.0, places=2)

    def test_delay_seconds_calculation_with_decimal_inputs(self):
        """Verify delay calculation handles Decimal and integer inputs safely."""
        raw_data = [
            {"current_travel_time_sec": Decimal("350"), "free_flow_travel_time_sec": Decimal("200")},
            {"current_travel_time_sec": 150, "free_flow_travel_time_sec": Decimal("200")},  # faster than free flow
            {"current_travel_time_sec": None, "free_flow_travel_time_sec": Decimal("200")},
        ]
        df = pd.DataFrame(raw_data)
        for col in ["current_travel_time_sec", "free_flow_travel_time_sec"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        delay = (df["current_travel_time_sec"] - df["free_flow_travel_time_sec"]).apply(
            lambda d: max(0, int(d)) if pd.notna(d) else 0
        ).tolist()

        self.assertEqual(delay[0], 150)
        self.assertEqual(delay[1], 0)  # clamped to 0
        self.assertEqual(delay[2], 0)

    def test_load_road_segments_converts_decimal_length(self):
        """Verify load_road_segments converts Decimal length_km to float."""
        mock_row = {
            "segment_id": "SEG_NAG_01",
            "location_id": "LOC_NAGPUR",
            "road_name": "Wardha Road",
            "segment_type": "HIGHWAY",
            "speed_limit_kmh": 70,
            "capacity_vph": 4500,
            "length_km": Decimal("6.00"),
        }
        with patch("dashboard.data_loader.get_db_cursor") as mock_cursor_ctx:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [mock_row]
            mock_cursor_ctx.return_value.__enter__.return_value = mock_cursor

            df = load_road_segments()
            self.assertEqual(df["length_km"].dtype, np.float64)
            self.assertAlmostEqual(float(df["length_km"].iloc[0]), 6.0)

    def test_render_urban_analytics_with_live_mysql_data(self):
        """Verifies render_urban_analytics runs to completion without raising exceptions on live MySQL data."""
        def mock_columns(spec, **kwargs):
            count = spec if isinstance(spec, int) else len(spec)
            return [MagicMock() for _ in range(count)]

        with patch("streamlit.columns", side_effect=mock_columns), \
             patch("streamlit.date_input", return_value=[None, None]), \
             patch("streamlit.plotly_chart"), \
             patch("streamlit.dataframe"), \
             patch("streamlit.markdown"), \
             patch("streamlit.info"), \
             patch("streamlit.success"), \
             patch("streamlit.warning"), \
             patch("streamlit.error"):
            # Should run without any TypeError or ValueError
            render_urban_analytics()


if __name__ == "__main__":
    unittest.main()
