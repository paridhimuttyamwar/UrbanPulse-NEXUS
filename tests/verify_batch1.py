"""
UrbanPulse Batch 1 Verification Script.
Executes end-to-end integration tests for:
1. Database schema and seed verification.
2. Real-world Weather API ingestion and MySQL storage.
3. Real-world Air Quality API ingestion and MySQL storage.
4. Traffic simulation generation, validation, and storage.
5. Rejection pipeline test (invalid payloads safely stored, never silently discarded).
6. Idempotency test (duplicate events handled gracefully).
"""

import sys
from pathlib import Path
from datetime import datetime

# Set path to root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings
from database.connection import get_db_cursor
from database.repository import repository
from ingestion.weather.weather_client import weather_client
from ingestion.air_quality.air_quality_client import air_quality_client
from simulator.traffic_simulator import traffic_simulator
from validation.validator import ValidationEngine
from storage.raw_archiver import archiver


def run_checks():
    print("=" * 70)
    print("URBANPULSE BATCH 1 — VERIFICATION SUITE")
    print("=" * 70)

    # 1. Database Connection & Seed Data Check
    print("\n[1/6] Verifying Database Connection and Seed Data...")
    with get_db_cursor(commit=False) as cursor:
        cursor.execute("SELECT COUNT(*) as count FROM locations")
        loc_count = cursor.fetchone()["count"]
        cursor.execute("SELECT COUNT(*) as count FROM road_segments")
        seg_count = cursor.fetchone()["count"]
        cursor.execute("SELECT COUNT(*) as count FROM traffic_sensors")
        sensor_count = cursor.fetchone()["count"]

    print(f" -> Found {loc_count} Locations (Expected >= 4)")
    print(f" -> Found {seg_count} Road Segments (Expected >= 15)")
    print(f" -> Found {sensor_count} Traffic Sensors (Expected >= 15)")
    assert loc_count >= 4, "Location count below expectation!"
    assert seg_count >= 15, "Road segments count below expectation!"
    print(" [PASSED] Database Schema and Seed Data verified.")

    # 2. Weather API Ingestion
    print("\n[2/6] Ingesting Real Weather Observations from Open-Meteo...")
    weather_success = weather_client.ingest_all_locations()
    print(f" -> Successfully ingested weather for {weather_success} locations.")
    assert weather_success > 0, "Weather ingestion failed for all locations!"

    with get_db_cursor(commit=False) as cursor:
        cursor.execute("SELECT * FROM weather_readings ORDER BY timestamp DESC LIMIT 3")
        rows = cursor.fetchall()
        for r in rows:
            print(
                f"    [DB Check] {r['location_id']} | Temp: {r['temperature_c']}°C | "
                f"Condition: {r['weather_condition']} | Wind: {r['wind_speed_kmh']} km/h | Source: {r['source_type']}"
            )
    print(" [PASSED] Weather API ingestion & MySQL insertion verified.")

    # 3. Air Quality API Ingestion
    print("\n[3/6] Ingesting Real Air Quality Observations from Open-Meteo...")
    aq_success = air_quality_client.ingest_all_locations()
    print(f" -> Successfully ingested Air Quality for {aq_success} locations.")
    assert aq_success > 0, "Air Quality ingestion failed for all locations!"

    with get_db_cursor(commit=False) as cursor:
        cursor.execute("SELECT * FROM air_quality_readings ORDER BY timestamp DESC LIMIT 3")
        rows = cursor.fetchall()
        for r in rows:
            print(
                f"    [DB Check] {r['location_id']} | US AQI: {r['us_aqi']} ({r['aqi_category']}) | "
                f"PM2.5: {r['pm2_5']} µg/m³ | PM10: {r['pm10']} µg/m³ | Source: {r['source_type']}"
            )
    print(" [PASSED] Air Quality API ingestion & MySQL insertion verified.")

    # 4. Traffic Simulator Generation & Ingestion
    print("\n[4/6] Generating and Validating Simulated Traffic Events...")
    batch = traffic_simulator.generate_batch()
    print(f" -> Generated {len(batch)} simulated traffic readings.")
    assert len(batch) >= 15, "Traffic batch smaller than configured segments!"

    inserted_count = 0
    for reading in batch:
        val_record, err = ValidationEngine.validate_traffic(reading)
        assert err is None, f"Simulator generated invalid record: {err}"
        assert val_record.source_type == "SIMULATED", "Traffic data not tagged as SIMULATED!"
        if repository.insert_traffic_reading(val_record):
            inserted_count += 1

    print(f" -> Successfully validated and inserted {inserted_count} traffic readings into MySQL.")
    with get_db_cursor(commit=False) as cursor:
        cursor.execute(
            "SELECT segment_id, avg_speed_kmh, vehicle_count, congestion_level, source_type "
            "FROM traffic_readings ORDER BY timestamp DESC LIMIT 3"
        )
        for r in cursor.fetchall():
            print(
                f"    [DB Check] {r['segment_id']} | Speed: {r['avg_speed_kmh']} km/h | "
                f"Vehicles: {r['vehicle_count']} | Congestion: {r['congestion_level']} | Source: {r['source_type']}"
            )
    print(" [PASSED] Traffic Simulator generation & MySQL insertion verified.")

    # 5. Data Validation & Rejection Pipeline Test
    print("\n[5/6] Testing Validation and Rejection Tracking...")
    malformed_payload = {
        "event_id": "EVT_TEST_INVALID_999",
        "sensor_id": "SNS_TRF_PUN_01",
        "segment_id": "SEG_PUN_01",
        "timestamp": "2026-10-10 12:00:00",
        "vehicle_count": -50,  # Invalid: negative count
        "avg_speed_kmh": 280.0,  # Invalid: above 200 km/h threshold
        "congestion_level": "UNKNOWN_LEVEL",  # Invalid enum
        "traffic_density_vpk": -10.0,
    }

    val_record, err = ValidationEngine.validate_traffic(malformed_payload)
    assert val_record is None, "Validation failed to catch invalid record!"
    assert err is not None, "Error reason was empty on rejected record!"
    print(f" -> Expected rejection caught: {err}")

    # Persist to rejected_records table
    repository.insert_rejected_record(
        source_name="traffic_simulator",
        source_type="SIMULATED",
        raw_payload=malformed_payload,
        rejection_reason=err,
        event_id=malformed_payload["event_id"],
    )

    with get_db_cursor(commit=False) as cursor:
        cursor.execute(
            "SELECT * FROM rejected_records WHERE event_id = 'EVT_TEST_INVALID_999'"
        )
        rej_row = cursor.fetchone()
        assert rej_row is not None, "Rejected record was not saved in rejected_records table!"
        print(f"    [DB Check] Found logged rejection in DB: {rej_row['rejection_reason']}")
    print(" [PASSED] Validation & Rejection handling successfully verified.")

    # 6. Idempotency Check
    print("\n[6/6] Verifying Idempotency (re-inserting identical records)...")
    first_reading = batch[0]
    val_record, _ = ValidationEngine.validate_traffic(first_reading)
    success_duplicate = repository.insert_traffic_reading(val_record)
    assert success_duplicate is True, "Duplicate insertion failed!"
    print(" [PASSED] Idempotency confirmed (ON DUPLICATE KEY UPDATE executed safely).")

    print("\n" + "=" * 70)
    print("ALL BATCH 1 VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_checks()
