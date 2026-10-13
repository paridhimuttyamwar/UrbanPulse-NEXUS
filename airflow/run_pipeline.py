"""
UrbanPulse Lightweight Pipeline Runner.
Allows local command-line execution of Airflow batch workflows without
running heavy Docker daemons on 12 GB RAM machines.
"""

import argparse
import logging
import sys
from pathlib import Path

# Set root dir in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from airflow.dags.urbanpulse_weather_ingestion_dag import task_ingest_weather
from airflow.dags.urbanpulse_air_quality_ingestion_dag import task_ingest_air_quality
from airflow.dags.urbanpulse_hourly_traffic_dag import task_compute_traffic_metrics
from airflow.dags.urbanpulse_daily_environment_dag import task_compute_environment_metrics
from airflow.dags.urbanpulse_data_quality_dag import task_run_data_quality_checks

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PipelineRunner")


def run_job(job_name: str):
    logger.info(f"Triggering batch workflow: {job_name.upper()}")

    if job_name in ["weather", "all"]:
        logger.info("Executing task: Ingest Open-Meteo Weather...")
        w_count = task_ingest_weather()
        logger.info(f"Weather task completed: {w_count} records processed.")

    if job_name in ["air_quality", "all"]:
        logger.info("Executing task: Ingest Open-Meteo Air Quality...")
        aq_count = task_ingest_air_quality()
        logger.info(f"Air Quality task completed: {aq_count} records processed.")

    if job_name in ["traffic_metrics", "all"]:
        logger.info("Executing task: Compute Hourly Traffic Rollups...")
        trf_count = task_compute_traffic_metrics()
        logger.info(f"Traffic metrics task completed: {trf_count} records aggregated.")

    if job_name in ["environment_metrics", "all"]:
        logger.info("Executing task: Compute Daily Environmental Metrics...")
        env_count = task_compute_environment_metrics()
        logger.info(f"Environment metrics task completed: {env_count} records aggregated.")

    if job_name in ["data_quality", "all"]:
        logger.info("Executing task: Data Quality Audit...")
        dq_res = task_run_data_quality_checks()
        logger.info(f"Data quality task completed: {dq_res}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UrbanPulse Batch Pipeline Runner")
    parser.add_argument(
        "job",
        nargs="?",
        default="all",
        choices=["weather", "air_quality", "traffic_metrics", "environment_metrics", "data_quality", "all"],
        help="Batch workflow to execute (default: all)",
    )
    args = parser.parse_args()
    run_job(args.job)
