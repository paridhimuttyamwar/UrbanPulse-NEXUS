"""
Airflow DAG: UrbanPulse Daily Environmental Metrics
Aggregates daily meteorological and atmospheric quality trends into MySQL.
"""

from datetime import datetime, timedelta

try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
    HAS_AIRFLOW = True
except ImportError:
    HAS_AIRFLOW = False


def task_compute_environment_metrics():
    import sys
    from pathlib import Path
    import uuid

    root_dir = Path("/opt/airflow/urbanpulse") if Path("/opt/airflow/urbanpulse").is_dir() else Path(__file__).resolve().parent.parent.parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))

    from analytics.environment_analytics import environment_analytics
    from database.repository import repository

    run_id = f"RUN_ENV_AGG_{uuid.uuid4().hex[:12]}"
    start_time = datetime.utcnow()
    repository.log_pipeline_run(
        run_id=run_id,
        pipeline_name="daily_environment_metrics",
        status="STARTED",
        records_processed=0,
        records_rejected=0,
        started_at=start_time,
    )
    try:
        count = environment_analytics.compute_and_store_daily_metrics()
        repository.log_pipeline_run(
            run_id=run_id,
            pipeline_name="daily_environment_metrics",
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
            pipeline_name="daily_environment_metrics",
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
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    }

    with DAG(
        dag_id="urbanpulse_daily_environment_metrics",
        default_args=default_args,
        description="Compute and store daily environment aggregate metrics",
        schedule_interval="0 1 * * *",  # 01:00 AM UTC daily
        start_date=datetime(2026, 1, 1),
        catchup=False,
        tags=["urbanpulse", "analytics", "environment"],
    ) as dag:

        agg_task = PythonOperator(
            task_id="compute_daily_environmental_rollups",
            python_callable=task_compute_environment_metrics,
        )
