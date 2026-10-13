"""
Airflow DAG: UrbanPulse Hourly Traffic Metrics
Computes hourly traffic rollups, congestion indexes, and persists to MySQL.
"""

from datetime import datetime, timedelta

try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
    HAS_AIRFLOW = True
except ImportError:
    HAS_AIRFLOW = False


def task_compute_traffic_metrics():
    import sys
    from pathlib import Path
    import uuid

    root_dir = Path("/opt/airflow/urbanpulse") if Path("/opt/airflow/urbanpulse").is_dir() else Path(__file__).resolve().parent.parent.parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))

    from analytics.traffic_analytics import traffic_analytics
    from database.repository import repository

    run_id = f"RUN_TRF_AGG_{uuid.uuid4().hex[:12]}"
    start_time = datetime.utcnow()
    repository.log_pipeline_run(
        run_id=run_id,
        pipeline_name="hourly_traffic_metrics",
        status="STARTED",
        records_processed=0,
        records_rejected=0,
        started_at=start_time,
    )
    try:
        count = traffic_analytics.compute_and_store_hourly_metrics()
        repository.log_pipeline_run(
            run_id=run_id,
            pipeline_name="hourly_traffic_metrics",
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
            pipeline_name="hourly_traffic_metrics",
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
        "retry_delay": timedelta(minutes=1),
    }

    with DAG(
        dag_id="urbanpulse_hourly_traffic_metrics",
        default_args=default_args,
        description="Compute and store hourly traffic aggregated metrics",
        schedule_interval="15 * * * *",  # 15 minutes past every hour
        start_date=datetime(2026, 1, 1),
        catchup=False,
        tags=["urbanpulse", "analytics", "traffic"],
    ) as dag:

        agg_task = PythonOperator(
            task_id="compute_hourly_traffic_rollups",
            python_callable=task_compute_traffic_metrics,
        )
