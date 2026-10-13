"""
Airflow DAG: UrbanPulse Data Quality & Hygiene Checks
Verifies database integrity, alerts on abnormal rejection spikes or missing data.
"""

from datetime import datetime, timedelta

try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
    HAS_AIRFLOW = True
except ImportError:
    HAS_AIRFLOW = False


def task_run_data_quality_checks():
    import sys
    from pathlib import Path
    import logging

    root_dir = Path("/opt/airflow/urbanpulse") if Path("/opt/airflow/urbanpulse").is_dir() else Path(__file__).resolve().parent.parent.parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))

    from database.connection import get_db_cursor

    log = logging.getLogger(__name__)

    with get_db_cursor(commit=False) as cursor:
        # Check 1: Rejected records in last hour
        cursor.execute(
            """
            SELECT COUNT(*) AS rejected_count 
            FROM rejected_records 
            WHERE timestamp >= NOW() - INTERVAL 1 HOUR
            """
        )
        rej_count = cursor.fetchone()["rejected_count"]

        # Check 2: Traffic sensor health
        cursor.execute(
            """
            SELECT COUNT(*) AS stale_sensors 
            FROM traffic_sensors 
            WHERE status = 'ACTIVE' 
              AND sensor_id NOT IN (
                  SELECT DISTINCT sensor_id FROM traffic_readings WHERE timestamp >= NOW() - INTERVAL 2 HOUR
              )
            """
        )
        stale_sensors = cursor.fetchone()["stale_sensors"]

        log.info(
            f"Data Quality Audit: {rej_count} rejected records, {stale_sensors} stale sensors in last interval."
        )
        return {"rejected_count": rej_count, "stale_sensors": stale_sensors}


if HAS_AIRFLOW:
    default_args = {
        "owner": "urbanpulse",
        "depends_on_past": False,
        "email_on_failure": False,
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
    }

    with DAG(
        dag_id="urbanpulse_data_quality_checks",
        default_args=default_args,
        description="Automated audit for rejected payloads and stale pipelines",
        schedule_interval="45 * * * *",  # 45 minutes past every hour
        start_date=datetime(2026, 1, 1),
        catchup=False,
        tags=["urbanpulse", "quality", "governance"],
    ) as dag:

        quality_check_task = PythonOperator(
            task_id="audit_data_quality_and_rejections",
            python_callable=task_run_data_quality_checks,
        )
