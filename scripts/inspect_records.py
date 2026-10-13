import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from database.connection import get_db_connection

def main():
    with get_db_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT id, segment_id, avg_speed_kmh, free_flow_speed_kmh, current_travel_time_sec,
                   confidence_score, road_closure, event_id, timestamp, created_at, source_type
            FROM traffic_readings
            WHERE source_type = 'REAL_API'
            ORDER BY id ASC
        """)
        rows = cur.fetchall()
        print(f"Total REAL_API records: {len(rows)}")
        for r in rows:
            print(f"ID {r['id']:4d} | Seg: {r['segment_id']:10s} | Speed: {float(r['avg_speed_kmh']):5.1f} | FreeFlow: {float(r['free_flow_speed_kmh'] or 0):5.1f} | Time: {r['current_travel_time_sec']}s | Created: {r['created_at']} | Event: {r['event_id']}")

if __name__ == "__main__":
    main()
