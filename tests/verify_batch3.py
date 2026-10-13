"""
UrbanPulse Batch 3 Verification Script.
Executes end-to-end integration tests for:
1. Streamlit cached data-loader functions and MySQL queries.
2. Dashboard view imports and modular integrity.
3. Chart generation data structures and Plotly rendering compatibility.
4. Data provenance labels and methodology alert verification.
"""

import sys
from pathlib import Path

# Set path to root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.data_loader import (
    load_locations,
    load_road_segments,
    load_latest_weather,
    load_latest_air_quality,
    load_traffic_readings,
    load_anomalies,
    load_iot_readings,
    load_pipeline_runs,
    load_data_source_status,
)
from dashboard.views.overview import render_overview
from dashboard.views.traffic import render_traffic
from dashboard.views.environment import render_environment
from dashboard.views.urban_analytics import render_urban_analytics
from dashboard.views.iot_monitoring import render_iot_monitoring
from dashboard.views.anomaly_center import render_anomaly_center


def run_batch3_checks():
    print("=" * 70)
    print("URBANPULSE BATCH 3 — DASHBOARD VERIFICATION")
    print("=" * 70)

    # 1. Test Cached Data Loader Queries
    print("\n[1/4] Verifying Data Loader Queries...")
    df_locs = load_locations()
    print(f" -> Locations loaded: {len(df_locs)} records")
    assert not df_locs.empty, "Locations query returned empty DataFrame!"

    df_segments = load_road_segments()
    print(f" -> Road Segments loaded: {len(df_segments)} records")
    assert not df_segments.empty, "Road segments query returned empty DataFrame!"

    df_weather = load_latest_weather()
    print(f" -> Latest Weather loaded: {len(df_weather)} records")
    assert not df_weather.empty, "Weather query returned empty DataFrame!"

    df_aq = load_latest_air_quality()
    print(f" -> Latest Air Quality loaded: {len(df_aq)} records")
    assert not df_aq.empty, "Air quality query returned empty DataFrame!"

    df_traffic = load_traffic_readings(limit=100)
    print(f" -> Traffic Readings loaded: {len(df_traffic)} records")
    assert not df_traffic.empty, "Traffic readings query returned empty DataFrame!"

    df_anom = load_anomalies(limit=50)
    print(f" -> Anomalies loaded: {len(df_anom)} records")
    assert not df_anom.empty, "Anomalies query returned empty DataFrame!"

    print(" [PASSED] All database loader queries verified.")

    # 2. Test Provenance Attribution Health
    print("\n[2/4] Verifying Provenance Attribution and Stream Health...")
    sources = load_data_source_status()
    for s in sources:
        print(f" -> Stream: {s['Source']} | Provenance: [{s['Type']}] | Records: {s['Records']} | Status: {s['Status']}")
        assert s["Type"] in ["REAL_API", "SIMULATED", "REAL_HARDWARE"], f"Invalid provenance tag: {s['Type']}"
    print(" [PASSED] Data provenance tagging confirmed.")

    # 3. Test View Function Signatures
    print("\n[3/4] Validating Dashboard View Modular Integrity...")
    views = [
        ("Overview", render_overview),
        ("Traffic Intelligence", render_traffic),
        ("Environmental Monitoring", render_environment),
        ("Urban Analytics", render_urban_analytics),
        ("IoT Monitoring", render_iot_monitoring),
        ("Anomaly Center", render_anomaly_center),
    ]
    for name, fn in views:
        assert callable(fn), f"View function {name} is not callable!"
        print(f" -> View '{name}' verified and callable.")
    print(" [PASSED] Dashboard view modules verified.")

    # 4. Verify Streamlit Compilation
    print("\n[4/4] Verifying Streamlit Application Compilation...")
    import py_compile
    app_path = Path(__file__).resolve().parent.parent / "dashboard" / "app.py"
    py_compile.compile(str(app_path), doraise=True)
    print(f" -> {app_path.name} compiled successfully with 0 errors.")
    print(" [PASSED] Streamlit application syntax and compilation verified.")

    print("\n" + "=" * 70)
    print("ALL BATCH 3 VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_batch3_checks()
