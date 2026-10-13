"""
Controlled Probe Script for Recovering the 4 Excluded Corridors.
Tests candidate coordinates and zoom levels with strict budget tracking.
Calculates snapping distance (haversine) and inspects returned polyline.
"""

import math
import sys
from typing import Dict, Any, List
from config.settings import settings
from ingestion.traffic.tomtom_client import tomtom_client

def haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371000.0  # meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

CANDIDATES = [
    {
        "segment_id": "SEG_NAG_02",
        "name": "Sitabuldi Main Road",
        "lat": 21.1445,
        "lon": 79.0845,
        "zoom": 14,
    },
    {
        "segment_id": "SEG_NAG_05",
        "name": "Manish Nagar Main Road",
        "lat": 21.0856,
        "lon": 79.0803,
        "zoom": 12,
    },
    {
        "segment_id": "SEG_NAG_12",
        "name": "Nandanvan Main Road",
        "lat": 21.1350,
        "lon": 79.1248,
        "zoom": 12,
    },
    {
        "segment_id": "SEG_NAG_14",
        "name": "Civil Lines Road",
        "lat": 21.1548,
        "lon": 79.0748,
        "zoom": 12,
    },
]

def main():
    print("=== STARTING CONTROLLED PROBE FOR 4 EXCLUDED CORRIDORS ===")
    initial_usage = tomtom_client.budget_tracker.get_usage()
    print(f"Initial Usage: {initial_usage.get('requests_attempted')}/{initial_usage.get('monthly_budget')}")

    results = []

    for item in CANDIDATES:
        sid = item["segment_id"]
        name = item["name"]
        lat = item["lat"]
        lon = item["lon"]
        zoom = item["zoom"]

        print(f"\n--- Testing {sid} ({name}) at ({lat}, {lon}) with zoom {zoom} ---")
        ok, payload, err = tomtom_client.fetch_flow_segment_data(lat, lon, zoom=zoom)

        if not ok or not payload:
            print(f"FAILED: {err}")
            results.append({"segment_id": sid, "status": "FAIL", "error": err})
            continue

        flow = payload.get("flowSegmentData", {})
        frc = flow.get("frc")
        cur_spd = flow.get("currentSpeed")
        ff_spd = flow.get("freeFlowSpeed")
        cur_tt = flow.get("currentTravelTime")
        ff_tt = flow.get("freeFlowTravelTime")
        conf = flow.get("confidence")
        coords = flow.get("coordinates", {}).get("coordinate", [])

        # Find min distance to polyline
        min_dist = float("inf")
        closest_pt = None
        for pt in coords:
            d = haversine(lat, lon, pt["latitude"], pt["longitude"])
            if d < min_dist:
                min_dist = d
                closest_pt = pt

        print(f"SUCCESS: FRC={frc}, Speed={cur_spd}/{ff_spd} km/h, TT={cur_tt}/{ff_tt}s, Conf={conf}")
        print(f"Polyline points: {len(coords)}, Min snapping distance: {min_dist:.1f}m")
        if closest_pt:
            print(f"Closest point: ({closest_pt['latitude']}, {closest_pt['longitude']})")
        if coords:
            print(f"Start: ({coords[0]['latitude']:.5f}, {coords[0]['longitude']:.5f}) -> End: ({coords[-1]['latitude']:.5f}, {coords[-1]['longitude']:.5f})")

        results.append({
            "segment_id": sid,
            "name": name,
            "lat": lat,
            "lon": lon,
            "zoom": zoom,
            "frc": frc,
            "current_speed": cur_spd,
            "free_flow_speed": ff_spd,
            "snapping_distance_m": round(min_dist, 1),
            "polyline_count": len(coords),
            "status": "PASS",
        })

    final_usage = tomtom_client.budget_tracker.get_usage()
    print(f"\nFinal Usage: {final_usage.get('requests_attempted')}/{final_usage.get('monthly_budget')}")
    print("\nSummary of Probes:")
    for r in results:
        print(r)

if __name__ == "__main__":
    main()
