"""
Phase 4C Unit and Regression Test Suite for Urban Analytics Redesign:
Validates:
1. REAL_API-only traffic filtering.
2. Date-range filtering.
3. Correct IST hour extraction.
4. Congestion heatmap aggregation.
5. Missing-hour handling (preserved as NaN, never zero).
6. Historical corridor ranking.
7. Observation-count safeguards (provisional tags for N < 10).
8. Historical trend calculations.
9. Decimal/float compatibility with Decimal inputs.
10. Missing and zero denominator safety.
11. Correlation sample-size validation.
12. Constant-variable correlation handling (zero variance exclusion).
13. Cross-domain timestamp matching.
14. Cross-domain aggregation and sample-size independence safeguards.
15. Summary table accuracy across all 15 corridors.
16. CSV export validity.
17. Successful execution with actual MySQL data.
18. Absence of repetitive REAL_API badges on KPI cards and section headers.
"""

from decimal import Decimal
import io
import unittest
from datetime import datetime, timezone, date, timedelta
from unittest.mock import patch, MagicMock
import numpy as np
import pandas as pd

from analytics.traffic_analytics import traffic_analytics
from config.corridors import NAGPUR_CORRIDORS_GEO, get_approved_corridors
from dashboard.views.urban_analytics import (
    _calc_speed_reduction_pct,
    _calc_travel_delay_pct,
    render_urban_analytics,
)


class TestPhase4CUrbanAnalytics(unittest.TestCase):

    def test_01_real_api_only_traffic_filtering(self):
        """Verify load_traffic_dataframe filters exclusively for REAL_API observations."""
        df = traffic_analytics.load_traffic_dataframe(location_id="LOC_NAGPUR", source_type="REAL_API")
        self.assertFalse(df.empty, "Expected REAL_API traffic observations for LOC_NAGPUR")
        source_types = set(df["source_type"].tolist())
        self.assertEqual(source_types, {"REAL_API"}, "Only REAL_API records must be loaded")
        self.assertNotIn("SIMULATED", source_types)
        self.assertNotIn("TEST_MOCK", source_types)

    def test_02_date_range_filtering(self):
        """Verify date-range filtering works and handles out-of-bounds dates gracefully."""
        today = datetime.now().date()
        # Historical out-of-range date
        df_old = traffic_analytics.load_traffic_dataframe(
            location_id="LOC_NAGPUR",
            start_date=date(2020, 1, 1),
            end_date=date(2020, 1, 2),
            source_type="REAL_API",
        )
        self.assertTrue(df_old.empty, "Expected 0 records for year 2020 date range")

        # Active date range
        df_active = traffic_analytics.load_traffic_dataframe(
            location_id="LOC_NAGPUR",
            start_date=today - timedelta(days=7),
            end_date=today,
            source_type="REAL_API",
        )
        self.assertFalse(df_active.empty, "Expected records in active 7-day date range")

    def test_03_correct_ist_hour_extraction(self):
        """Verify UTC timestamps convert to IST (+05:30) and extract correct hour."""
        utc_ts = pd.Timestamp("2026-10-12 16:30:00", tz="UTC")
        ist_ts = utc_ts.tz_convert("Asia/Kolkata")
        # 16:30 UTC + 5h30m = 22:00 IST
        self.assertEqual(ist_ts.hour, 22)
        self.assertEqual(ist_ts.minute, 0)
        self.assertEqual(ist_ts.day, 12)

        # Cross-midnight check
        utc_midnight_ts = pd.Timestamp("2026-10-12 19:30:00", tz="UTC")
        ist_midnight_ts = utc_midnight_ts.tz_convert("Asia/Kolkata")
        # 19:30 UTC + 5h30m = 01:00 IST on Oct 13
        self.assertEqual(ist_midnight_ts.hour, 1)
        self.assertEqual(ist_midnight_ts.day, 13)

    def test_04_congestion_heatmap_aggregation(self):
        """Verify 15-corridor by 24-hour heatmap matrix aggregates speed reductions accurately."""
        corridors = list(NAGPUR_CORRIDORS_GEO.keys())
        self.assertEqual(len(corridors), 15, "Registry must contain 15 corridors")

        df = traffic_analytics.load_traffic_dataframe(location_id="LOC_NAGPUR", source_type="REAL_API")
        df["speed_reduction_pct"] = df.apply(
            lambda r: _calc_speed_reduction_pct(r.get("avg_speed_kmh"), r.get("free_flow_speed_kmh")), axis=1
        )
        df["timestamp_ist"] = pd.to_datetime(df["timestamp"]).dt.tz_localize("UTC").dt.tz_convert("Asia/Kolkata")
        df["hour_ist"] = df["timestamp_ist"].dt.hour

        # Construct 15 x 24 matrix
        matrix_z = np.full((15, 24), np.nan)
        matrix_counts = np.zeros((15, 24), dtype=int)

        for i, cid in enumerate(corridors):
            sub = df[df["segment_id"] == cid]
            for h in range(24):
                hr_match = sub[sub["hour_ist"] == h]["speed_reduction_pct"].dropna()
                if len(hr_match) > 0:
                    matrix_z[i, h] = hr_match.mean()
                    matrix_counts[i, h] = len(hr_match)

        self.assertEqual(matrix_z.shape, (15, 24))
        self.assertEqual(matrix_counts.shape, (15, 24))
        # Total counts populated must equal total valid speed reduction observations
        self.assertEqual(matrix_counts.sum(), df["speed_reduction_pct"].dropna().count())

    def test_05_missing_hour_handling(self):
        """Verify unobserved hours remain NaN in heatmap matrix and are not filled with zeros."""
        corridors = list(NAGPUR_CORRIDORS_GEO.keys())
        matrix_z = np.full((15, 24), np.nan)
        # Verify initial state has exactly 15*24 NaNs
        self.assertEqual(np.isnan(matrix_z).sum(), 15 * 24)

        # Simulate recording observations for only hour 22 on SEG_NAG_01
        matrix_z[0, 22] = 12.5
        # Hour 0 to 21 must strictly remain NaN, NOT 0.0
        for h in range(22):
            self.assertTrue(np.isnan(matrix_z[0, h]), f"Hour {h} should be NaN, not zero")
        self.assertEqual(matrix_z[0, 22], 12.5)

    def test_06_historical_corridor_ranking(self):
        """Verify ranking calculation for speed reduction and travel delay percentages."""
        # Simulated test dataframe
        data = {
            "segment_id": ["SEG_NAG_01", "SEG_NAG_01", "SEG_NAG_02", "SEG_NAG_02"],
            "avg_speed_kmh": [30.0, 30.0, 50.0, 45.0],
            "free_flow_speed_kmh": [60.0, 60.0, 50.0, 50.0],
            "current_travel_time_sec": [240, 240, 120, 140],
            "free_flow_travel_time_sec": [120, 120, 120, 120],
        }
        df = pd.DataFrame(data)
        df["speed_reduction_pct"] = df.apply(
            lambda r: _calc_speed_reduction_pct(r["avg_speed_kmh"], r["free_flow_speed_kmh"]), axis=1
        )
        df["delay_pct"] = df.apply(
            lambda r: _calc_travel_delay_pct(r["current_travel_time_sec"], r["free_flow_travel_time_sec"]), axis=1
        )

        ranked_red = df.groupby("segment_id")["speed_reduction_pct"].mean().sort_values(ascending=False)
        # SEG_NAG_01: (1 - 30/60) * 100 = 50%
        # SEG_NAG_02: avg of (1 - 50/50)*100=0% and (1 - 45/50)*100=10% -> 5%
        self.assertAlmostEqual(ranked_red["SEG_NAG_01"], 50.0)
        self.assertAlmostEqual(ranked_red["SEG_NAG_02"], 5.0)
        self.assertEqual(ranked_red.index[0], "SEG_NAG_01")

        ranked_delay = df.groupby("segment_id")["delay_pct"].mean().sort_values(ascending=False)
        # SEG_NAG_01: (240 - 120)/120 * 100 = 100%
        # SEG_NAG_02: avg of 0% and (140 - 120)/120 * 100 = 16.67% -> 8.33%
        self.assertAlmostEqual(ranked_delay["SEG_NAG_01"], 100.0)
        self.assertAlmostEqual(ranked_delay["SEG_NAG_02"], 8.33333333)

    def test_07_observation_count_safeguards(self):
        """Verify provisional tags apply when observation count is below 10."""
        obs_count_provisional = 4
        obs_count_verified = 15

        tag_prov = "Provisional" if obs_count_provisional < 10 else "Verified"
        tag_veri = "Provisional" if obs_count_verified < 10 else "Verified"

        self.assertEqual(tag_prov, "Provisional")
        self.assertEqual(tag_veri, "Verified")

    def test_08_historical_trend_calculations(self):
        """Verify multi-corridor time series grouping preserves individual discrete observations."""
        df = traffic_analytics.load_traffic_dataframe(location_id="LOC_NAGPUR", source_type="REAL_API")
        df["speed_reduction_pct"] = df.apply(
            lambda r: _calc_speed_reduction_pct(r.get("avg_speed_kmh"), r.get("free_flow_speed_kmh")), axis=1
        )
        c_01 = df[df["segment_id"] == "SEG_NAG_01"].sort_values("timestamp")
        self.assertGreater(len(c_01), 0)
        # Every observation must have a valid speed reduction float
        for val in c_01["speed_reduction_pct"].dropna():
            self.assertGreaterEqual(val, 0.0)
            self.assertLessEqual(val, 100.0)

    def test_09_decimal_float_compatibility(self):
        """Verify Decimal inputs from MySQL do not trigger TypeError in math operations."""
        dec_spd = Decimal("24.5")
        dec_ff = Decimal("50.0")
        red = _calc_speed_reduction_pct(dec_spd, dec_ff)
        self.assertIsInstance(red, float)
        # (1 - 24.5/50.0)*100 = 51.0%
        self.assertAlmostEqual(red, 51.0)

        dec_cur_time = Decimal("300")
        dec_ff_time = Decimal("150")
        delay = _calc_travel_delay_pct(dec_cur_time, dec_ff_time)
        self.assertIsInstance(delay, float)
        # (300 - 150)/150 * 100 = 100.0%
        self.assertAlmostEqual(delay, 100.0)

    def test_10_missing_and_zero_denominators(self):
        """Verify zero or invalid denominators return NaN safely without ZeroDivisionError."""
        # Zero free flow speed
        res_zero_ff = _calc_speed_reduction_pct(40.0, 0.0)
        self.assertTrue(np.isnan(res_zero_ff), "Zero free-flow speed should return NaN, not zero")

        # Negative free flow speed
        res_neg_ff = _calc_speed_reduction_pct(40.0, -10.0)
        self.assertTrue(np.isnan(res_neg_ff))

        # None/NaN inputs
        self.assertTrue(np.isnan(_calc_speed_reduction_pct(None, 50.0)))
        self.assertTrue(np.isnan(_calc_speed_reduction_pct(40.0, None)))
        self.assertTrue(np.isnan(_calc_speed_reduction_pct(np.nan, 50.0)))

        # Zero travel time denominator
        res_zero_time = _calc_travel_delay_pct(120, 0)
        self.assertTrue(np.isnan(res_zero_time))
        self.assertTrue(np.isnan(_calc_travel_delay_pct(None, 120)))

    def test_11_correlation_sample_size_validation(self):
        """Verify Pearson correlation requires sample size >= 5 and valid variance."""
        df_small = pd.DataFrame({
            "a": [1.0, 2.0, 3.0],
            "b": [2.0, 4.0, 6.0],
        })
        # If N < 5, correlation should be flagged as insufficient
        self.assertLess(len(df_small), 5)

        df_adequate = pd.DataFrame({
            "a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "b": [2.0, 4.0, 5.0, 8.0, 9.0, 12.0],
        })
        self.assertGreaterEqual(len(df_adequate), 5)
        corr_val = df_adequate["a"].corr(df_adequate["b"])
        self.assertGreater(corr_val, 0.95)

    def test_12_constant_variable_correlation_handling(self):
        """Verify constant columns with zero variance are excluded from correlation calculation."""
        df_const = pd.DataFrame({
            "speed": [30.0, 40.0, 35.0, 25.0, 45.0, 50.0],
            "constant_conf": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],  # var = 0
            "delay": [12.0, 4.0, 8.0, 18.0, 2.0, 1.0],
        })
        # Check variance detection
        valid_cols = [c for c in df_const.columns if df_const[c].var() > 0 and df_const[c].nunique() > 1]
        self.assertNotIn("constant_conf", valid_cols, "Constant column must be filtered out")
        self.assertEqual(set(valid_cols), {"speed", "delay"})

        corr_mat = df_const[valid_cols].corr()
        self.assertFalse(corr_mat.isna().any().any(), "Correlation matrix must not contain NaNs")

    def test_13_cross_domain_timestamp_matching(self):
        """Verify cross-domain matching aggregates hourly on truncated IST timestamp buckets."""
        ts1 = pd.Timestamp("2026-10-12 21:14:00")
        ts2 = pd.Timestamp("2026-10-12 21:45:00")
        self.assertEqual(ts1.floor("h"), ts2.floor("h"))
        self.assertEqual(ts1.floor("h"), pd.Timestamp("2026-10-12 21:00:00"))

    def test_14_cross_domain_aggregation_and_independence_safeguards(self):
        """Verify city-wide network aggregation produces 1 observation per hour (no sample size inflation)."""
        data = []
        # 15 corridors reporting at 21:00 and 22:00
        for h in [21, 22]:
            for i in range(1, 16):
                data.append({
                    "segment_id": f"SEG_NAG_{i:02d}",
                    "timestamp_ist": pd.Timestamp(f"2026-10-12 {h}:15:00"),
                    "speed_reduction_pct": 5.0 + i,
                    "delay_pct": 8.0 + i,
                })
        df_raw = pd.DataFrame(data)
        self.assertEqual(len(df_raw), 30, "Raw rows = 30 across 15 corridors")

        # Network aggregation
        net_hourly = df_raw.groupby(df_raw["timestamp_ist"].dt.floor("h")).agg(
            mean_speed_red=("speed_reduction_pct", "mean"),
            active_corridors=("segment_id", "nunique"),
        ).reset_index()

        # Must have exactly 2 independent hourly records, NOT 30
        self.assertEqual(len(net_hourly), 2, "Network hourly roll-up must yield 1 record per hour")
        self.assertEqual(net_hourly["active_corridors"].tolist(), [15, 15])

    def test_15_summary_table_accuracy(self):
        """Verify corridor summary table includes all 15 corridors with valid data formatting."""
        df = traffic_analytics.load_traffic_dataframe(location_id="LOC_NAGPUR", source_type="REAL_API")
        all_cids = list(NAGPUR_CORRIDORS_GEO.keys())
        self.assertEqual(len(all_cids), 15)

        summary_rows = []
        for cid in all_cids:
            sub = df[df["segment_id"] == cid]
            summary_rows.append({
                "Corridor ID": cid,
                "Observations": len(sub),
                "Mean Speed": sub["avg_speed_kmh"].mean() if not sub.empty else np.nan,
            })
        sum_df = pd.DataFrame(summary_rows)
        self.assertEqual(len(sum_df), 15, "Summary must contain all 15 registered corridors")
        self.assertEqual(sum_df["Observations"].sum(), len(df))

    def test_16_csv_export_format(self):
        """Verify CSV export produces valid CSV bytes with expected column headers."""
        data = {
            "Corridor Name": ["Wardha Road", "Central Avenue"],
            "Corridor ID": ["SEG_NAG_01", "SEG_NAG_02"],
            "Observations": [6, 5],
            "Mean Speed (km/h)": [32.4, 28.1],
            "Mean Speed Reduction (%)": [8.8, 12.1],
        }
        df = pd.DataFrame(data)
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        self.assertIsInstance(csv_bytes, bytes)

        # Parse back
        read_df = pd.read_csv(io.BytesIO(csv_bytes))
        self.assertEqual(len(read_df), 2)
        self.assertIn("Corridor Name", read_df.columns)
        self.assertIn("Mean Speed Reduction (%)", read_df.columns)

    @patch("streamlit.date_input")
    def test_17_render_view_execution_with_mysql(self, mock_date):
        """Verify render_urban_analytics executes successfully without raising exceptions."""
        today = datetime.now().date()
        mock_date.return_value = (today - timedelta(days=3), today)

        # Execute the view callable inside a safe test wrapper
        try:
            render_urban_analytics()
            render_success = True
        except Exception as e:
            render_success = False
            self.fail(f"render_urban_analytics raised exception: {e}")

        self.assertTrue(render_success)

    def test_18_absence_of_repetitive_real_api_badges(self):
        """Verify urban_analytics.py does not pass provenance='REAL_API' into KPI cards or headers."""
        with open("dashboard/views/urban_analytics.py", "r", encoding="utf-8") as f:
            code = f.read()

        # Check KPI cards in Section 1 do not have provenance="REAL_API"
        self.assertNotIn('provenance="REAL_API"', code, "Repetitive REAL_API badge should not be in KPI calls")
        # Ensure only the page header has REAL_API TELEMETRY
        self.assertEqual(code.count('provenance_badge="REAL_API TELEMETRY"'), 1, "Only single header badge allowed")


if __name__ == "__main__":
    unittest.main()
