"""
UrbanPulse Database Initializer.
Executes schema.sql and seed_data.sql idempotently.
"""

import sys
from pathlib import Path
import logging

# Ensure urbanpulse root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings
from database.connection import get_db_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def execute_sql_file(file_path: Path, use_database: bool = False):
    """Executes a multi-statement SQL script file safely."""
    logger.info(f"Executing SQL file: {file_path.name}")
    with open(file_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # Split commands by semicolon, ignoring empty statements
    statements = [stmt.strip() for stmt in sql_content.split(";") if stmt.strip()]

    with get_db_connection(use_database=use_database) as conn:
        cursor = conn.cursor()
        try:
            for statement in statements:
                # Skip comments only statements
                clean_lines = [
                    line for line in statement.splitlines()
                    if not line.strip().startswith("--") and line.strip()
                ]
                if not clean_lines:
                    continue
                clean_stmt = "\n".join(clean_lines)
                cursor.execute(clean_stmt)
            conn.commit()
            logger.info(f"Successfully executed {file_path.name}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Error executing statement from {file_path.name}: {e}")
            raise
        finally:
            cursor.close()


def initialize_database():
    """Initializes the urbanpulse schema and loads seed data."""
    logger.info("Initializing UrbanPulse Database...")
    db_dir = Path(__file__).resolve().parent
    schema_file = db_dir / "schema.sql"
    seed_file = db_dir / "seed_data.sql"

    # Step 1: Run schema without requiring the DB to exist beforehand
    execute_sql_file(schema_file, use_database=False)

    # Step 2: Seed initial locations, road segments, and sensors
    execute_sql_file(seed_file, use_database=True)

    logger.info("UrbanPulse Database initialized and seeded successfully.")


if __name__ == "__main__":
    initialize_database()
