"""
UrbanPulse Traffic Streaming Producer.
Publishes simulated urban road network events to Kafka topic 'urbanpulse.traffic.raw'.
Includes local raw JSONL archival, connection resilience, and configurable event rates.
"""

import json
import logging
import time
from typing import Optional
from kafka import KafkaProducer
from kafka.errors import KafkaError

from config.settings import settings
from simulator.traffic_simulator import traffic_simulator
from storage.raw_archiver import archiver

logger = logging.getLogger(__name__)


class TrafficKafkaProducer:
    def __init__(self, bootstrap_servers: Optional[str] = None):
        self.bootstrap_servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self.topic = settings.KAFKA_TRAFFIC_TOPIC
        self.producer: Optional[KafkaProducer] = None
        self._initialize_producer()

    def _initialize_producer(self):
        """Attempts to initialize Kafka Producer."""
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                retries=3,
                request_timeout_ms=5000,
            )
            logger.info(f"Kafka Producer connected to {self.bootstrap_servers}")
        except Exception as e:
            logger.warning(
                f"Kafka broker at {self.bootstrap_servers} unavailable: {e}. "
                "Producer running in fallback/standalone mode."
            )
            self.producer = None

    def publish_reading(self, reading: dict) -> bool:
        """
        Publishes a single traffic reading to Kafka and archives raw event to disk.
        """
        event_id = reading["event_id"]
        segment_id = reading["segment_id"]

        # Always archive raw payload to disk
        archiver.archive_raw(
            event_id=event_id,
            source="traffic_simulator",
            payload=reading,
            source_type="SIMULATED",
        )

        if self.producer:
            try:
                future = self.producer.send(
                    self.topic,
                    key=segment_id,
                    value=reading,
                )
                self.producer.flush(timeout=5)
                logger.info(
                    f"Published event {event_id} to Kafka topic {self.topic} [Segment: {segment_id}]"
                )
                return True
            except KafkaError as ke:
                logger.error(f"Failed to publish to Kafka: {ke}")
                return False
        else:
            logger.info(
                f"[Fallback Mode] Generated & archived traffic event {event_id} for {segment_id}"
            )
            return True

    def run(self, iterations: Optional[int] = None, interval_seconds: Optional[float] = None):
        """Runs the simulator producer for N iterations or continuously."""
        delay = interval_seconds or settings.SIMULATOR_FREQUENCY_SECONDS
        count = 0
        logger.info(
            f"Starting traffic producer (Interval: {delay}s, Iterations: {iterations or 'infinite'})..."
        )

        try:
            while True:
                batch = traffic_simulator.generate_batch()
                for reading in batch:
                    self.publish_reading(reading)

                count += 1
                if iterations and count >= iterations:
                    logger.info(f"Completed {iterations} iterations.")
                    break
                time.sleep(delay)
        except KeyboardInterrupt:
            logger.info("Traffic producer stopped by user.")
        finally:
            self.close()

    def close(self):
        if self.producer:
            self.producer.flush()
            self.producer.close()
            logger.info("Kafka Producer closed.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    prod = TrafficKafkaProducer()
    prod.run(iterations=2)
