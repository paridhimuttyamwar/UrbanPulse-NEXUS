"""
UrbanPulse Database Connection Manager.
Provides connection pooling and context managers for MySQL queries.
"""

import logging
from contextlib import contextmanager
import mysql.connector
from mysql.connector import pooling
from config.settings import settings

logger = logging.getLogger(__name__)

# Connection pool setup
_connection_pool = None


def get_db_pool():
    global _connection_pool
    if _connection_pool is None:
        try:
            _connection_pool = pooling.MySQLConnectionPool(
                pool_name="urbanpulse_pool",
                pool_size=5,
                pool_reset_session=True,
                host=settings.MYSQL_HOST,
                port=settings.MYSQL_PORT,
                user=settings.MYSQL_USER,
                password=settings.MYSQL_PASSWORD,
                database=settings.MYSQL_DATABASE,
            )
            logger.info("MySQL connection pool established successfully.")
        except Exception as e:
            logger.error(f"Failed to create MySQL connection pool: {e}")
            raise
    return _connection_pool


@contextmanager
def get_db_connection(use_database: bool = True):
    """
    Context manager yielding a database connection.
    If use_database is False, connects to MySQL server without selecting a DB.
    """
    if not use_database:
        conn = mysql.connector.connect(
            host=settings.MYSQL_HOST,
            port=settings.MYSQL_PORT,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
        )
        try:
            yield conn
        finally:
            conn.close()
    else:
        pool = get_db_pool()
        conn = pool.get_connection()
        try:
            yield conn
        finally:
            conn.close()


@contextmanager
def get_db_cursor(commit: bool = False, dictionary: bool = True):
    """
    Context manager yielding a cursor and handling commit/rollback.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=dictionary, buffered=True)
        try:
            yield cursor
            if commit:
                conn.commit()
        except Exception as e:
            if commit:
                conn.rollback()
            logger.error(f"Database error during cursor execution: {e}")
            raise
        finally:
            cursor.close()
