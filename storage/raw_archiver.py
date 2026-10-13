"""
UrbanPulse Local Storage Archiver.
Archives raw, processed, and rejected records in append-only JSON Lines format.
Designed with an abstraction layer for future S3 integration.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from config.settings import settings

logger = logging.getLogger(__name__)


class StorageArchiver:
    def __init__(self):
        self.raw_dir = settings.RAW_DATA_DIR
        self.processed_dir = settings.PROCESSED_DATA_DIR
        self.rejected_dir = settings.REJECTED_DATA_DIR

    def _get_daily_file_path(self, base_dir: Path, source_name: str) -> Path:
        """Partition by date and source name: data/<stage>/<source_name>_YYYY-MM-DD.jsonl"""
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        file_path = base_dir / f"{source_name}_{date_str}.jsonl"
        return file_path

    def archive_raw(
        self,
        event_id: str,
        source: str,
        payload: Dict[str, Any],
        source_type: str = "REAL_API",
    ) -> Path:
        """
        Archives raw inbound payload before validation/transformation.
        Preserves original payload, event ID, source, and ingestion timestamp.
        """
        record = {
            "event_id": event_id,
            "source": source,
            "source_type": source_type,
            "ingestion_timestamp": datetime.utcnow().isoformat(),
            "payload": payload,
        }
        target_file = self._get_daily_file_path(self.raw_dir, source)
        with open(target_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        return target_file

    def archive_processed(
        self,
        event_id: str,
        source: str,
        record_data: Dict[str, Any],
    ) -> Path:
        """Archives successfully processed records."""
        record = {
            "event_id": event_id,
            "source": source,
            "processed_timestamp": datetime.utcnow().isoformat(),
            "data": record_data,
        }
        target_file = self._get_daily_file_path(self.processed_dir, source)
        with open(target_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        return target_file

    def archive_rejected(
        self,
        event_id: Optional[str],
        source: str,
        source_type: str,
        raw_payload: Any,
        rejection_reason: str,
    ) -> Path:
        """Archives rejected payloads that failed validation."""
        record = {
            "event_id": event_id,
            "source": source,
            "source_type": source_type,
            "rejection_timestamp": datetime.utcnow().isoformat(),
            "rejection_reason": rejection_reason,
            "raw_payload": raw_payload,
        }
        target_file = self._get_daily_file_path(self.rejected_dir, source)
        with open(target_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        return target_file


archiver = StorageArchiver()
