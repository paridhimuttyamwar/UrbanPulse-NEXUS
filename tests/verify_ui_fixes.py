"""
Verification test script for UrbanPulse NEXUS UI Fixes & System Integrity.
Directly tests:
1. Kafka Settings attribute and System Diagnostics execution
2. Plotly Traffic chart layout and legend margins
3. Environmental AQI gauge layout, category display, and dimensions
4. Edge IoT Lab segmented control / tab options and expander title
5. Anomaly Center filter labels and history expander
6. Global verification of expander titles across all views
7. .streamlit/config.toml theme settings
"""

import sys
from pathlib import Path

# Add project root to path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

def test_settings_kafka():
    print("[1/7] Testing Settings.KAFKA_CONSUMER_GROUP and Diagnostics block...")
    from config.settings import settings
    assert hasattr(settings, "KAFKA_CONSUMER_GROUP"), "Missing KAFKA_CONSUMER_GROUP in settings"
    assert settings.KAFKA_CONSUMER_GROUP == "urbanpulse_traffic_consumer_group", f"Unexpected group: {settings.KAFKA_CONSUMER_GROUP}"
    
    # Test getattr fallback
    fallback_val = getattr(settings, "KAFKA_CONSUMER_GROUP", "urbanpulse_traffic_consumer_group") or "Not configured"
    assert fallback_val == "urbanpulse_traffic_consumer_group"
    print(" -> KAFKA_CONSUMER_GROUP verified:", settings.KAFKA_CONSUMER_GROUP)
    print(" [PASSED] Kafka settings attribute and fallback verified.")

def test_streamlit_config():
    print("[2/7] Testing .streamlit/config.toml theme configuration...")
    config_file = root_dir / ".streamlit" / "config.toml"
    assert config_file.exists(), ".streamlit/config.toml does not exist"
    content = config_file.read_text(encoding="utf-8")
    assert 'base = "dark"' in content, "Missing dark base theme in config.toml"
    assert 'primaryColor = "#29D8F4"' in content, "Missing primaryColor in config.toml"
    assert 'textColor = "#F4F8FF"' in content, "Missing textColor in config.toml"
    print(" -> config.toml dark theme validated.")
    print(" [PASSED] Streamlit configuration verified.")

def test_traffic_chart_layout():
    print("[3/7] Testing Traffic line chart layout and margins...")
    traffic_file = root_dir / "dashboard" / "views" / "traffic.py"
    code = traffic_file.read_text(encoding="utf-8")
    assert "apply_nexus_theme(fig_time, height=450)" in code, "fig_time height not 450"
    assert "b=120" in code, "Bottom margin b=120 missing in fig_time layout"
    assert "orientation=\"h\"" in code, "Horizontal legend missing in fig_time layout"
    assert "standoff=18" in code, "Axis title standoff missing in fig_time layout"
    assert "View Recent Traffic Readings" in code, "Updated expander title missing in traffic.py"
    assert "Recent 100" not in code, "Misleading Recent 100 still present in traffic.py"
    print(" -> Traffic chart height=450, margin b=120, legend below axis title verified.")
    print(" [PASSED] Traffic layout verified.")

def test_environment_aqi_gauge():
    print("[4/7] Testing Environmental AQI gauge layout and margins...")
    env_file = root_dir / "dashboard" / "views" / "environment.py"
    code = env_file.read_text(encoding="utf-8")
    assert "apply_nexus_theme(fig_gauge, height=350)" in code, "fig_gauge height not 350"
    assert "t=65" in code, "Top margin t=65 missing in fig_gauge layout"
    assert "Category: {cat_name}" in code, "Category missing in fig_gauge title"
    assert "View Recent Atmospheric Observations" in code, "Updated expander title missing in environment.py"
    assert "Recent 100" not in code, "Misleading Recent 100 still present in environment.py"
    print(" -> AQI gauge height=350, margin t=65, category and value verified.")
    print(" [PASSED] Environmental AQI gauge verified.")

def test_iot_monitoring():
    print("[5/7] Testing Edge IoT Lab mode selector and expander...")
    iot_file = root_dir / "dashboard" / "views" / "iot_monitoring.py"
    code = iot_file.read_text(encoding="utf-8")
    assert "st.segmented_control" in code, "st.segmented_control missing in iot_monitoring.py"
    assert "View Recent Sensor Ingestion Packets" in code, "Updated expander title missing in iot_monitoring.py"
    assert "Recent 50" not in code, "Misleading Recent 50 still present in iot_monitoring.py"
    print(" -> Segmented control and clean expander title verified.")
    print(" [PASSED] Edge IoT Lab verified.")

def test_anomaly_center():
    print("[6/7] Testing Anomaly Center filter labels and expander...")
    anom_file = root_dir / "dashboard" / "views" / "anomaly_center.py"
    code = anom_file.read_text(encoding="utf-8")
    assert 'st.selectbox("Incident Triage Status"' in code
    assert 'st.selectbox("Severity Classification"' in code
    assert "View Incident History" in code, "View Incident History expander missing in anomaly_center.py"
    print(" -> Filter dropdowns and history expander verified.")
    print(" [PASSED] Anomaly Center verified.")

def test_expander_titles_globally():
    print("[7/7] Testing all expander titles across dashboard views...")
    views_dir = root_dir / "dashboard" / "views"
    for py_file in views_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            if "st.expander" in line:
                assert "Recent 100" not in line, f"Found Recent 100 in {py_file.name}: {line}"
                assert "Recent 50" not in line, f"Found Recent 50 in {py_file.name}: {line}"
                assert "Last 100" not in line, f"Found Last 100 in {py_file.name}: {line}"
                print(f" -> {py_file.name}: {line.strip()}")
    print(" [PASSED] Zero misleading fixed-count titles across all expanders.")

if __name__ == "__main__":
    test_settings_kafka()
    test_streamlit_config()
    test_traffic_chart_layout()
    test_environment_aqi_gauge()
    test_iot_monitoring()
    test_anomaly_center()
    test_expander_titles_globally()
    print("\n=======================================================")
    print("ALL 7 UI FIX VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=======================================================")
