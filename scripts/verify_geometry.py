import sys, os, json, math
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config.corridors import NAGPUR_CORRIDORS_GEO
from database.connection import get_db_connection

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000  # meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def main():
    # Load raw events
    raw_by_event = {}
    with open('data/raw/tomtom_traffic_flow_2026-10-12.jsonl', 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip(): continue
            d = json.loads(line)
            evt = d.get('event_id')
            if evt:
                raw_by_event[evt] = d

    print(f"Loaded {len(raw_by_event)} raw events from raw archive.")

    with get_db_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT id, segment_id, avg_speed_kmh, free_flow_speed_kmh, current_travel_time_sec,
                   confidence_score, road_closure, event_id, timestamp, created_at
            FROM traffic_readings
            WHERE source_type = 'REAL_API'
            ORDER BY id ASC
        """)
        db_rows = cur.fetchall()

    print(f"Loaded {len(db_rows)} REAL_API rows from database.\n")
    print("=" * 110)
    print(f"{'DB ID':<6} | {'Seg ID':<10} | {'Road Name':<32} | {'Dist (m)':<8} | {'Match Type':<16} | {'Coords #':<8} | {'Event ID':<28}")
    print("=" * 110)

    for r in db_rows:
        seg_id = r['segment_id']
        geo = NAGPUR_CORRIDORS_GEO.get(seg_id, {})
        target_lat = geo.get('latitude')
        target_lon = geo.get('longitude')
        road_name = geo.get('road_name', 'Unknown')
        evt = r['event_id']

        raw_entry = raw_by_event.get(evt)
        if not raw_entry:
            print(f"{r['id']:<6} | {seg_id:<10} | {road_name[:32]:<32} | {'N/A':<8} | {'NO RAW ARCHIVE':<16} | {'N/A':<8} | {evt:<28}")
            continue

        fsd = raw_entry.get('payload', {}).get('flowSegmentData', {})
        coords = fsd.get('coordinates', {}).get('coordinate', [])
        num_coords = len(coords)

        # Find closest coordinate in returned geometry to query point
        min_dist = float('inf')
        for c in coords:
            d = haversine_m(target_lat, target_lon, c['latitude'], c['longitude'])
            if d < min_dist:
                min_dist = d

        # Match type classification:
        # If min distance to geometry polyline <= 100m: Verified Exact Match
        # If min distance <= 350m: Approximate / Adjacent Road Match
        # Else: Discrepancy
        if min_dist <= 150:
            match_type = "VERIFIED MATCH"
        elif min_dist <= 400:
            match_type = "APPROXIMATE"
        else:
            match_type = "DISCREPANCY"

        print(f"{r['id']:<6} | {seg_id:<10} | {road_name[:32]:<32} | {min_dist:<8.1f} | {match_type:<16} | {num_coords:<8} | {evt:<28}")

if __name__ == "__main__":
    main()
