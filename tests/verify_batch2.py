"""
UrbanPulse Batch 2 Verification Script.
Executes end-to-end integration tests for:
1. Streaming pipeline producer & consumer processing.
2. Rule-based anomaly detection engine (traffic gridlock, poor AQI, extreme heat).
3. Pandas analytics & database rollup generation (hourly traffic, daily environment).
4. Cross-domain analytics & correlation calculation with caveat labels.
5. Batch orchestration pipeline runs & telemetry logging (Airflow runner).
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Set path to root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.connection import get_db_cursor
from database.repository import repository
from streaming.producers.traffic_producer import TrafficKafkaProducer
from streaming.consumers.traffic_consumer import TrafficKafkaConsumer
from anomaly_detection.rule_engine import anomaly_engine
from analytics.traffic_analytics import traffic_analytics
from analytics.environment_analytics import environment_analytics
from analytics.cross_domain_analytics import cross_domain_analytics
from airflow.run_pipeline import run_job
from simulator.traffic_simulator import traffic_simulator
from validation.validator import ValidationEngine


def run_batch2_checks():
    print("=" * 70)
    print("URBANPULSE BATCH 2 — DATA ENGINEERING VERIFICATION")
    print("=" * 70)

    # 1. Streaming Pipeline Verification
    print("\n[1/5] Verifying Streaming Pipeline (Producer -> Consumer Logic)...")
    producer = TrafficKafkaProducer()
    consumer = TrafficKafkaConsumer()

    # Generate test reading
    test_reading = traffic_simulator.generate_single_reading(
        {"segment_id": "SEG_PUN_01", "sensor_id": "SNS_TRF_PUN_01", "speed_limit_kmh": 40, "capacity_vph": 2200, "length_km": 2.5}
    )
    published = producer.publish_reading(test_reading)
    assert published is True, "Producer failed to publish/archive reading!"

    # Consume/Process payload directly through consumer pipeline
    processed = consumer.process_message_payload(test_reading)
    assert processed is True, "Consumer failed to process and store traffic reading!"

    with get_db_cursor(commit=False) as cursor:
        cursor.execute(
            "SELECT * FROM traffic_readings WHERE event_id = %(event_id)s",
            {"event_id": test_reading["event_id"]}
        )
        row = cursor.fetchone()
        assert row is not None, "Reading not found in MySQL traffic_readings!"
        print(f" -> Successfully processed streaming event: {row['event_id']} (Segment: {row['segment_id']}, Speed: {row['avg_speed_kmh']} km/h)")
    print(" [PASSED] Streaming producer and consumer pipeline verified.")

    # 2. Anomaly Detection Engine Verification
    print("\n[2/5] Testing Rule-Based Anomaly Detection...")
    # Test Severe Congestion anomaly
    severe_reading = {
        "segment_id": "SEG_PUN_04",
        "avg_speed_kmh": 6.5,
        "congestion_level": "SEVERE",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    }
    anom_trf_id = anomaly_engine.check_traffic_reading(severe_reading)
    assert anom_trf_id is not None, "Failed to trigger severe congestion anomaly!"

    # Test Hazardous AQI anomaly
    hazard_aq_reading = {
        "location_id": "LOC_DELHI",
        "us_aqi": 340,
        "pm2_5": 285.0,
        "timestamp": datetime.utcnow().isoformat(),
    }
    anom_aq_id = anomaly_engine.check_air_quality_reading(hazard_aq_reading)
    assert anom_aq_id is not None, "Failed to trigger hazardous air quality anomaly!"

    with get_db_cursor(commit=False) as cursor:
        cursor.execute(
            "SELECT anomaly_id, anomaly_type, severity, source_type, description FROM anomalies WHERE anomaly_id IN (%(t_id)s, %(a_id)s)",
            {"t_id": anom_trf_id, "a_id": anom_aq_id}
        )
        anom_rows = cursor.fetchall()
        assert len(anom_rows) == 2, "Anomalies not saved to MySQL anomalies table!"
        for a in anom_rows:
            print(f"    [DB Alert] {a['anomaly_id']} | Type: {a['anomaly_type']} | Severity: {a['severity']} | Source: {a['source_type']}")
    print(" [PASSED] Rule-based anomaly engine verified.")

    # 3. Simulate Historical Batch for Analytics
    print("\n[3/5] Populating Multi-Hour Simulated Data for Aggregations...")
    # Generate 2 days of simulated history to feed analytics rollups
    sim_count = 0
    for reading in traffic_simulator.simulate_historical_days(days=1, interval_minutes=60):
        val_rec, err = ValidationEngine.validate_traffic(reading)
        if val_rec:
            repository.insert_traffic_reading(val_rec)
            sim_count += 1
    print(f" -> Populated {sim_count} historical traffic events across 24 hours.")

    # 4. Pandas Analytics & MySQL Aggregation Rollups
    print("\n[4/5] Executing Pandas Hourly & Daily Aggregations...")
    trf_rollups = traffic_analytics.compute_and_store_hourly_metrics()
    print(f" -> Computed and stored {trf_rollups} hourly traffic metric records.")
    assert trf_rollups > 0, "No hourly traffic metrics computed!"

    env_rollups = environment_analytics.compute_and_store_daily_metrics()
    print(f" -> Computed and stored {env_rollups} daily environmental metric records.")
    assert env_rollups > 0, "No daily environmental metrics computed!"

    corr_df, caveat = cross_domain_analytics.calculate_correlation_matrix()
    print(f" -> Computed cross-domain correlation matrix ({corr_df.shape[0]}x{corr_df.shape[1]}).")
    print(f"    Notice: {caveat[:80]}...")
    print(" [PASSED] Pandas analytics and aggregations verified.")

    # 5. Batch Orchestration & Telemetry (Airflow Runner)
    print("\n[5/5] Executing Airflow Batch Orchestration Pipeline...")
    run_job("all")

    with get_db_cursor(commit=False) as cursor:
        cursor.execute("SELECT pipeline_name, status, records_processed, started_at FROM pipeline_runs ORDER BY started_at DESC LIMIT 5")
        pipeline_logs = cursor.fetchall()
        assert len(pipeline_logs) > 0, "No pipeline telemetry runs logged in MySQL!"
        for p in pipeline_logs:
            print(f"    [Telemetry] Pipeline: {p['pipeline_name']} | Status: {p['status']} | Processed: {p['records_processed']}")
    print(" [PASSED] Batch orchestration and pipeline telemetry verified.")

    print("\n" + "=" * 70)
    print("ALL BATCH 2 VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_batch2_checks()
