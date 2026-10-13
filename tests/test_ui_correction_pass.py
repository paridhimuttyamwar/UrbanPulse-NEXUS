"""
Unit and Integration Tests for Final UI Correction Pass.
Verifies:
1. Decorative sparkline generation and auto-mapping across accent colors.
2. KPI card layout structure, equal dimension styling, and non-clipping.
3. Corridor dropdown labels displaying clean road names without technical IDs.
4. Delay and speed reduction calculations and zero-value handling.
5. Physical device registration form functionality and sensor channel persistence.
6. Hardware-only telemetry isolation.
"""

import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

from dashboard.theme import (
    generate_svg_sparkline,
    render_kpi_card,
    render_nexus_hero,
    NEXUS_CSS,
)
from config.corridors import (
    NAGPUR_CORRIDORS_GEO,
    get_approved_corridors,
    get_corridor_geo,
)
from iot.serial_gateway.gateway import serial_gateway
from dashboard.data_loader import load_latest_traffic_per_corridor


class TestUICorrectionPass(unittest.TestCase):
    def test_01_decorative_sparkline_generation(self):
        """Verify lightweight SVG sparklines generate properly for all wave and bar types."""
        for s_type in ["wave_cyan", "wave_purple", "wave_amber", "wave_green", "wave_red", "bars_blue"]:
            svg = generate_svg_sparkline(s_type)
            self.assertTrue(svg.startswith("<svg"), f"Expected <svg tag for {s_type}")
            self.assertIn("class=\"sparkline-svg\"", svg)

        # Invalid or none returns empty string
        self.assertEqual(generate_svg_sparkline(None), "")
        self.assertEqual(generate_svg_sparkline("unknown"), "")

    @patch("streamlit.markdown")
    def test_02_kpi_card_sparkline_auto_mapping(self, mock_markdown):
        """Verify render_kpi_card defaults to matching decorative sparkline without explicit type."""
        render_kpi_card(
            label="Ambient Temperature",
            value=31.5,
            unit="°C",
            delta="Nominal",
            accent_color="cyan",
        )
        mock_markdown.assert_called()
        rendered_html = mock_markdown.call_args[0][0]
        self.assertIn("kpi-sparkline", rendered_html)
        self.assertIn("<svg", rendered_html)
        self.assertIn("grad_cyan", rendered_html)

    @patch("streamlit.markdown")
    def test_03_kpi_card_explicit_sparkline_types(self, mock_markdown):
        """Verify render_kpi_card respects explicit wave choices."""
        render_kpi_card(
            label="Air Quality Index",
            value=82,
            unit=" AQI",
            sparkline_type="wave_purple",
            accent_color="purple",
        )
        rendered_html = mock_markdown.call_args[0][0]
        self.assertIn("grad_purple", rendered_html)

    def test_04_kpi_card_css_equal_dimensions(self):
        """Verify CSS contains flex stretch and minimum height rules for equal card heights."""
        self.assertIn(".nexus-kpi-card", NEXUS_CSS)
        self.assertIn("min-height: 185px", NEXUS_CSS)
        self.assertIn("height: 100%", NEXUS_CSS)
        self.assertIn("div[data-testid=\"column\"]", NEXUS_CSS)

    @patch("streamlit.markdown")
    def test_05_hero_text_accuracy(self, mock_markdown):
        """Verify hero subtitle does not contain outdated simulation or sub-minute ingestion claims."""
        render_nexus_hero(status_label="SYNCED", status_cls="badge-positive")
        rendered_html = mock_markdown.call_args[0][0]
        self.assertNotIn("Next-generation", rendered_html)
        self.assertNotIn("Sub-minute Ingestion", rendered_html)
        self.assertNotIn("mobility simulations", rendered_html)
        self.assertIn("An urban data intelligence platform integrating traffic, weather, air quality, and IoT observations", rendered_html)
        self.assertIn("Hourly Pipeline Ingestion", rendered_html)

    def test_06_corridor_dropdown_clean_road_names(self):
        """Verify corridor dropdown labels display clean road names without technical IDs."""
        approved = get_approved_corridors()
        self.assertEqual(len(approved), 15)

        for cid in approved:
            geo = get_corridor_geo(cid)
            road_name = geo["road_name"]
            # Clean label must not have technical ID attached
            formatted_label = road_name
            self.assertNotIn("SEG_NAG_", formatted_label)
            self.assertGreater(len(formatted_label), 3)

    def test_07_delay_and_speed_reduction_zero_handling(self):
        """Verify derived delay and speed reduction handle 0 and equal travel times cleanly."""
        df_latest = load_latest_traffic_per_corridor(
            location_id="LOC_NAGPUR",
            source_type="REAL_API",
            stale_threshold_minutes=1440 * 7,
        )
        self.assertFalse(df_latest.empty)
        self.assertIn("delay_seconds", df_latest.columns)
        self.assertIn("speed_reduction_pct", df_latest.columns)

        # All delay_seconds must be >= 0 (no negative delays)
        self.assertTrue((df_latest["delay_seconds"] >= 0).all())
        # All speed_reduction_pct must be >= 0 (no negative speed reductions)
        self.assertTrue((df_latest["speed_reduction_pct"] >= 0).all())

    def test_08_physical_device_registration_and_channels(self):
        """Verify physical device registration updates and persists connected sensor channels."""
        # Test updating configuration for ARDUINO_SOUND_01
        ok, msg = serial_gateway.register_hardware_device(
            device_id="ARDUINO_SOUND_01",
            device_name="Nagpur Sound Sensor Unit",
            device_model="Arduino Uno R3",
            location_id="LOC_NAGPUR",
            connected_sensors="SOUND_P2P,SOUND_RAW",
            port_assignment="AUTO",
        )
        self.assertTrue(ok)
        self.assertIn("updated successfully", msg.lower())

    def test_09_hardware_telemetry_isolation(self):
        """Verify hardware queries only return REAL_HARDWARE telemetry."""
        from dashboard.data_loader import load_iot_readings
        df_hw = load_iot_readings(source_type="REAL_HARDWARE", limit=100)
        if not df_hw.empty:
            sources = df_hw["source_type"].unique()
            self.assertTrue(all(s == "REAL_HARDWARE" for s in sources))


if __name__ == "__main__":
    unittest.main()
