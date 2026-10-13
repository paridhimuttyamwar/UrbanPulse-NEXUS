"""
UrbanPulse Traffic Streaming Consumer.
Consumes messages from Kafka topic 'urbanpulse.traffic.raw',
validates payloads, persists idempotently into MySQL, evaluates real-time anomalies,
and commits consumer offsets after successful persistence (at-least-once guarantee).
"""

import json
import logging
import time
from typing import Any, Dict, Optional
from kafka import KafkaConsumer
from kafka.errors import KafkaError

from config.settings import settings
from validation.validator import ValidationEngine
from database.repository import repository
from storage.raw_archiver import archiver

logger = logging.getLogger(__name__)


class TrafficKafkaConsumer:
    def __init__(
        self,
        bootstrap_servers: Optional[str] = None,
        group_id: str = "urbanpulse_traffic_consumer_group",
    ):
        self.bootstrap_servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self.topic = settings.KAFKA_TRAFFIC_TOPIC
        self.group_id = group_id
        self.consumer: Optional[KafkaConsumer] = None

    def initialize_consumer(self, timeout_ms: int = 5000) -> bool:
        """Initializes connection to Kafka cluster."""
        try:
            self.consumer = KafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset="earliest",
                enable_auto_commit=False,
                consumer_timeout_ms=timeout_ms,
                api_version=(2, 6, 0),
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            )
            logger.info(
                f"Kafka Consumer connected to {self.bootstrap_servers} on topic '{self.topic}'"
            )
            return True
        except Exception as e:
            logger.warning(
                f"Could not connect Kafka Consumer to {self.bootstrap_servers}: {e}"
            )
            self.consumer = None
            return False

    def process_message_payload(self, payload: Dict[str, Any]) -> bool:
        """
        Core ingestion & validation pipeline for a traffic event payload:
        1. Validate payload schema.
        2. If invalid: record to rejected_records and disk.
        3. If valid: write idempotently to MySQL traffic_readings and archive processed record.
        """
        event_id = payload.get("event_id", "UNKNOWN")

        # 1. Validation
        val_record, err = ValidationEngine.validate_traffic(payload)
        if not val_record:
            logger.warning(f"Consumer rejecting invalid traffic payload [{event_id}]: {err}")
            repository.insert_rejected_record(
                source_name="kafka_traffic_consumer",
                source_type="SIMULATED",
                raw_payload=payload,
                rejection_reason=err or "Schema validation error",
                event_id=event_id,
            )
            return False

        # 2. Idempotent DB Insert
        try:
            repository.insert_traffic_reading(val_record)
            archiver.archive_processed(
                event_id=val_record.event_id,
                source="kafka_traffic_consumer",
                record_data=val_record.model_dump(),
            )
            logger.debug(
                f"Consumed & stored traffic event {val_record.event_id} for segment {val_record.segment_id}"
            )
            # Anomaly Detection Integration (safe, non-blocking)
            try:
                from anomaly_detection.rule_engine import anomaly_engine
                anomaly_engine.check_traffic_reading(val_record.model_dump())
            except Exception as anom_err:
                logger.warning(f"Traffic anomaly evaluation deferred: {anom_err}")

            return True
        except Exception as e:
            logger.error(f"Failed to persist traffic event {event_id} into MySQL: {e}")
            raise

    def consume_records(self, max_records: Optional[int] = None) -> int:
        """Consumes records from Kafka and processes them with manual offset commits."""
        if not self.consumer:
            if not self.initialize_consumer():
                logger.error("Cannot consume records: Kafka Consumer not connected.")
                return 0

        processed_count = 0
        try:
            for message in self.consumer:
                payload = message.value
                success = self.process_message_payload(payload)
                if success:
                    processed_count += 1

                # At-least-once delivery guarantee: commit after processing
                self.consumer.commit()

                if max_records and processed_count >= max_records:
                    break
        except Exception:
               logger.exception("Error during Kafka consumption")
        finally:
            logger.info(f"Consumer batch finished. Processed {processed_count} messages.")

        return processed_count

    def close(self):
        if self.consumer:
            self.consumer.close()
            logger.info("Kafka Consumer closed.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    cons = TrafficKafkaConsumer()
    cons.consume_records(max_records=5)
