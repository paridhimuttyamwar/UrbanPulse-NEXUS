import sys, os, json, math
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config.corridors import NAGPUR_CORRIDORS_GEO

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def main():
    target_segments = ["SEG_NAG_02", "SEG_NAG_05", "SEG_NAG_07", "SEG_NAG_12", "SEG_NAG_14"]

    # Load raw events from file
    events = []
    with open('data/raw/tomtom_traffic_flow_2026-10-12.jsonl', 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip(): continue
            d = json.loads(line)
            events.append(d)

    # From MySQL or event IDs, find the genuine batch event for each
    from database.connection import get_db_cursor
    with get_db_cursor(commit=False) as cur:
        cur.execute("SELECT id, segment_id, event_id FROM traffic_readings WHERE source_type = 'REAL_API'")
        db_rows = {r['segment_id']: r['event_id'] for r in cur.fetchall()}

    for seg in target_segments:
        geo = NAGPUR_CORRIDORS_GEO[seg]
        cur_lat = geo['latitude']
        cur_lon = geo['longitude']
        road = geo['road_name']
        evt = db_rows.get(seg)

        # find event payload
        matching_payload = None
        for e in events:
            if e.get('event_id') == evt:
                matching_payload = e.get('payload', {}).get('flowSegmentData', {})
                break

        if not matching_payload:
            print(f"[{seg}] No raw payload found.")
            continue

        coords = matching_payload.get('coordinates', {}).get('coordinate', [])
        frc = matching_payload.get('frc')
        cur_spd = matching_payload.get('currentSpeed')
        ff_spd = matching_payload.get('freeFlowSpeed')
        print(f"\n=======================================================")
        print(f"Segment: {seg} | Road: {road}")
        print(f"Configured Query Point: ({cur_lat:.5f}, {cur_lon:.5f})")
        print(f"TomTom Returned: FRC={frc}, Speed={cur_spd} km/h, FF={ff_spd} km/h, Total Coords={len(coords)}")
        
        # Find closest coord and center of coords
        min_d = float('inf')
        closest_coord = None
        for c in coords:
            d = haversine_m(cur_lat, cur_lon, c['latitude'], c['longitude'])
            if d < min_d:
                min_d = d
                closest_coord = c

        print(f"Minimum distance from query point to polyline: {min_d:.1f} m")
        print(f"Closest polyline coordinate: ({closest_coord['latitude']:.5f}, {closest_coord['longitude']:.5f})")
        # Print bounding box of polyline
        lats = [c['latitude'] for c in coords]
        lons = [c['longitude'] for c in coords]
        print(f"Polyline Latitude Range:  [{min(lats):.5f}, {max(lats):.5f}] (span: {(max(lats)-min(lats))*111000:.0f}m)")
        print(f"Polyline Longitude Range: [{min(lons):.5f}, {max(lons):.5f}] (span: {(max(lons)-min(lons))*104000:.0f}m)")
        # Sample coordinates along the polyline
        step = max(1, len(coords)//5)
        print("Sample polyline coordinates:")
        for idx in range(0, len(coords), step):
            c = coords[idx]
            dist_to_query = haversine_m(cur_lat, cur_lon, c['latitude'], c['longitude'])
            print(f"  [{idx:3d}] ({c['latitude']:.5f}, {c['longitude']:.5f}) -> {dist_to_query:.1f}m from query point")

if __name__ == '__main__':
    main()
