"""
Airflow DAG: UrbanPulse Weather Ingestion
Periodically fetches real meteorological data from Open-Meteo API.
"""

from datetime import datetime, timedelta

try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
    HAS_AIRFLOW = True
except ImportError:
    HAS_AIRFLOW = False


def task_ingest_weather():
    import sys
    from pathlib import Path
    import uuid

    # Dynamically find urbanpulse root
    root_dir = Path("/opt/airflow/urbanpulse") if Path("/opt/airflow/urbanpulse").is_dir() else Path(__file__).resolve().parent.parent.parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))

    from ingestion.weather.weather_client import weather_client
    from database.repository import repository

    run_id = f"RUN_WTH_{uuid.uuid4().hex[:12]}"
    start_time = datetime.utcnow()
    repository.log_pipeline_run(
        run_id=run_id,
        pipeline_name="weather_ingestion",
        status="STARTED",
        records_processed=0,
        records_rejected=0,
        started_at=start_time,
    )
    try:
        count = weather_client.ingest_all_locations()
        repository.log_pipeline_run(
            run_id=run_id,
            pipeline_name="weather_ingestion",
            status="SUCCESS",
            records_processed=count,
            records_rejected=0,
            started_at=start_time,
            finished_at=datetime.utcnow(),
        )
        return count
    except Exception as e:
        repository.log_pipeline_run(
            run_id=run_id,
            pipeline_name="weather_ingestion",
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
        "retries": 3,
        "retry_delay": timedelta(minutes=2),
        "execution_timeout": timedelta(minutes=10),
    }

    with DAG(
        dag_id="urbanpulse_weather_ingestion",
        default_args=default_args,
        description="Fetch and persist Open-Meteo weather observations",
        schedule_interval="0 * * * *",  # Hourly
        start_date=datetime(2026, 1, 1),
        catchup=False,
        tags=["urbanpulse", "weather", "batch"],
    ) as dag:

        ingest_task = PythonOperator(
            task_id="ingest_open_meteo_weather",
            python_callable=task_ingest_weather,
        )
