"""
Airflow DAG: UrbanPulse TomTom Real Traffic Ingestion
Periodically fetches real-world traffic observations from TomTom Traffic Flow API
across 15 monitored Nagpur corridors with strict rate budgeting and quota protection.
"""

from datetime import datetime, timedelta

try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
    HAS_AIRFLOW = True
except ImportError:
    HAS_AIRFLOW = False


def task_ingest_tomtom_traffic():
    """
    Ingests live traffic observations across all 15 registered Nagpur corridors.
    Checks monthly safety budget before each request, records run telemetry,
    and logs outcomes to pipeline_runs.
    """
    import sys
    from pathlib import Path
    import uuid

    # Dynamically find urbanpulse root directory
    root_dir = (
        Path("/opt/airflow/urbanpulse")
        if Path("/opt/airflow/urbanpulse").is_dir()
        else Path(__file__).resolve().parent.parent.parent
    )
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))

    from ingestion.traffic.tomtom_client import tomtom_client
    from database.repository import repository

    run_id = f"RUN_TRF_TOMTOM_{uuid.uuid4().hex[:12]}"
    start_time = datetime.utcnow()

    repository.log_pipeline_run(
        run_id=run_id,
        pipeline_name="tomtom_traffic_ingestion",
        status="STARTED",
        records_processed=0,
        records_rejected=0,
        started_at=start_time,
    )

    try:
        results = tomtom_client.ingest_all_corridors()
        successful_count = results.get("successful", 0)
        failed_count = results.get("failed", 0)

        status = "SUCCESS" if successful_count > 0 else ("FAILED" if failed_count > 0 else "SUCCESS")
        error_msg = None
        if failed_count > 0:
            error_msg = f"Partial failure: {failed_count} corridors failed: {results.get('failed_segments')}"

        repository.log_pipeline_run(
            run_id=run_id,
            pipeline_name="tomtom_traffic_ingestion",
            status=status,
            records_processed=successful_count,
            records_rejected=failed_count,
            started_at=start_time,
            finished_at=datetime.utcnow(),
            error_message=error_msg,
        )
        return successful_count

    except Exception as e:
        repository.log_pipeline_run(
            run_id=run_id,
            pipeline_name="tomtom_traffic_ingestion",
            status="FAILED",
            records_processed=0,
            records_rejected=0,
            started_at=start_time,
            finished_at=datetime.utcnow(),
            error_message=str(e),
        )
        raise


if HAS_AIRFLOW:
    default_args = {
        "owner": "urbanpulse",
        "depends_on_past": False,
        "email_on_failure": False,
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
        "execution_timeout": timedelta(minutes=5),
    }

    with DAG(
        dag_id="urbanpulse_tomtom_traffic_ingestion",
        default_args=default_args,
        description="Fetch and persist genuine TomTom traffic observations across verified corridors",
        schedule_interval="0 * * * *",  # Once per hour (at the top of the hour)
        start_date=datetime(2026, 1, 1),
        catchup=False,
        max_active_runs=1,
        is_paused_upon_creation=False,  # Unpaused active state for automated execution
        tags=["urbanpulse", "traffic", "tomtom", "real_api"],
    ) as dag:

        ingest_task = PythonOperator(
            task_id="ingest_tomtom_corridors",
            python_callable=task_ingest_tomtom_traffic,
        )
