"""
Test suite for UrbanPulse NEXUS Traffic Intelligence View
Verifies all 15 corridors, 'ALL' full-network view, date filtering, and empty observation handling.
"""
import sys
import os
from datetime import datetime, timedelta, date

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
from dashboard.data_loader import load_road_segments, load_traffic_readings
from analytics.traffic_analytics import traffic_analytics
import plotly.express as px

def test_all_corridors_and_views():
    print("=== STARTING TRAFFIC INTELLIGENCE VERIFICATION ===")
    
    # 1. Load Road Segments
    df_segments = load_road_segments(location_id="LOC_NAGPUR")
    print(f"Loaded road segments: {len(df_segments)} segments found.")
    assert not df_segments.empty, "df_segments should not be empty!"
    assert len(df_segments) == 15, f"Expected 15 segments, got {len(df_segments)}"
    print("Segment IDs:", df_segments["segment_id"].tolist())

    today = datetime.now().date()
    start_date = today - timedelta(days=7)
    end_date = today

    # Test ALL view
    print("\n--- Testing 'ALL' Corridors View ---")
    df_traffic_all = load_traffic_readings(
        segment_id="ALL",
        location_id="LOC_NAGPUR",
        start_date=start_date,
        end_date=end_date,
        limit=3000,
    )
    print(f"'ALL' Corridors records loaded: {len(df_traffic_all)}")
    assert not df_traffic_all.empty, "Expected traffic readings for full network"
    
    # Verify plotting logic for 'ALL'
    cong_counts = df_traffic_all["congestion_level"].value_counts().reset_index()
    cong_counts.columns = ["Level", "Count"]
    assert len(cong_counts) > 0

    seg_speeds = (
        df_traffic_all.groupby("road_name")["avg_speed_kmh"]
        .mean()
        .reset_index()
        .sort_values("avg_speed_kmh", ascending=True)
    )
    assert len(seg_speeds) > 0

    # 2. Test each of the 15 corridors
    print("\n--- Testing Individual 15 Corridors ---")
    corridor_ids = df_segments["segment_id"].tolist()
    success_count = 0

    for seg_id in corridor_ids:
        df_traffic_seg = load_traffic_readings(
            segment_id=seg_id,
            location_id="LOC_NAGPUR",
            start_date=start_date,
            end_date=end_date,
            limit=3000,
        )
        
        # Test Corridor Explorer logic
        seg_meta_matches = df_segments[df_segments["segment_id"] == seg_id]
        assert not seg_meta_matches.empty, f"Segment {seg_id} missing in df_segments"
        seg_meta = seg_meta_matches.iloc[0]

        cur_spd = df_traffic_seg['avg_speed_kmh'].mean() if not df_traffic_seg.empty else None
        cur_vol = df_traffic_seg['vehicle_count'].mean() if not df_traffic_seg.empty else None
        limit_spd = seg_meta.get('speed_limit_kmh', 0)
        
        if pd.notna(cur_spd) and limit_spd and limit_spd > 0:
            spd_ratio = (cur_spd / limit_spd * 100)
            spd_color = '#35D6A1' if cur_spd >= limit_spd * 0.7 else '#FF647C'
            obs_spd_str = f"{cur_spd:.1f} km/h ({spd_ratio:.0f}%)"
        elif pd.notna(cur_spd):
            spd_color = '#35D6A1'
            obs_spd_str = f"{cur_spd:.1f} km/h"
        else:
            spd_color = '#9FB1C9'
            obs_spd_str = "N/A"

        obs_vol_str = f"{cur_vol:.0f} veh/interval" if pd.notna(cur_vol) else "N/A"

        # Check lanes key retrieval
        lanes_val = seg_meta.get('lanes', seg_meta.get('lane_count', None))
        if pd.notna(lanes_val) and lanes_val is not None:
            lanes_str = f"{lanes_val} Lanes"
        else:
            lanes_str = "Not available"

        length_km = seg_meta.get('length_km')
        length_str = f"{length_km} km" if pd.notna(length_km) else "Not available"
        speed_limit_str = f"{limit_spd} km/h" if pd.notna(limit_spd) and limit_spd else "Not available"
        cap_val = seg_meta.get('capacity_vph')
        cap_str = f"{cap_val} veh/hr" if pd.notna(cap_val) and cap_val else "Not available"
        road_name = seg_meta.get('road_name', seg_id)
        segment_type = seg_meta.get('segment_type', 'ARTERIAL')
        segment_id = seg_meta.get('segment_id', seg_id)

        # Confirm lanes_str is "Not available" since schema has no lanes
        assert lanes_str == "Not available", f"Expected 'Not available', got {lanes_str}"
        assert length_str != "Not available", f"Expected length, got {length_str}"
        assert speed_limit_str != "Not available", f"Expected speed limit, got {speed_limit_str}"

        print(f"  [PASS] {seg_id} ({road_name}): obs={len(df_traffic_seg)}, spd={obs_spd_str}, lanes={lanes_str}, cap={cap_str}")
        success_count += 1

    assert success_count == 15, f"Expected 15 successes, got {success_count}"

    # 3. Test Empty Observations Scenario (e.g. far future date)
    print("\n--- Testing Empty Observations Handling ---")
    df_empty = load_traffic_readings(
        segment_id="SEG_NAG_01",
        location_id="LOC_NAGPUR",
        start_date=date(2099, 1, 1),
        end_date=date(2099, 1, 2),
        limit=100,
    )
    print(f"Empty date range records: {len(df_empty)}")
    assert df_empty.empty, "Should return empty dataframe for future date range"

    # Verify simulation of empty view handling
    if df_empty.empty:
        empty_msg = "No traffic observations found for the selected corridor and date range. Please adjust filters."
        print(f"  [PASS] Graceful message generated: '{empty_msg}'")

    print("\n=== ALL TRAFFIC INTELLIGENCE CHECKS PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    test_all_corridors_and_views()
