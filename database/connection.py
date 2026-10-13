"""
UrbanPulse Database Connection Manager.
Provides connection pooling and context managers for MySQL queries.
"""

import logging
from contextlib import contextmanager
import mysql.connector
from mysql.connector import pooling
import certifi
from config.settings import settings

logger = logging.getLogger(__name__)

# Connection pool setup
_connection_pool = None


def get_db_pool():
    global _connection_pool
    if _connection_pool is None:
        if settings.is_cloud:
            # Explicit Cloud Mode Enforcement:
            target_host = settings.TIDB_HOST
            if not target_host or target_host in ("localhost", "127.0.0.1"):
                raise ValueError(
                    "URBANPULSE_ENV='cloud' prohibits connecting to localhost or using an empty host. "
                    "A valid remote TiDB Cloud host (TIDB_HOST) is required."
                )
            user = settings.TIDB_USER
            password = settings.TIDB_PASSWORD
            port = settings.TIDB_PORT
            database = settings.TIDB_DATABASE or "urbanpulse"
            if not user or not password:
                raise ValueError("URBANPULSE_ENV='cloud' requires valid cloud database credentials (TIDB_USER, TIDB_PASSWORD).")

            try:
                pool_config = {
                    "pool_name": "urbanpulse_cloud_pool",
                    "pool_size": 5,
                    "pool_reset_session": True,
                    "host": target_host,
                    "port": port,
                    "user": user,
                    "password": password,
                    "database": database,
                    "ssl_ca": certifi.where(),
                    "ssl_verify_cert": True,
                    "ssl_verify_identity": True,
                }
                _connection_pool = pooling.MySQLConnectionPool(**pool_config)
                logger.info("Connected to TiDB Cloud with verified TLS (URBANPULSE_ENV='cloud').")
            except Exception as e:
                logger.error(f"Failed to create TiDB Cloud connection pool: {e}")
                raise
        else:
            # Local Mode (Default): connects to local MySQL without SSL
            try:
                _connection_pool = pooling.MySQLConnectionPool(
                    pool_name="urbanpulse_local_pool",
                    pool_size=5,
                    pool_reset_session=True,
                    host=settings.MYSQL_HOST,
                    port=settings.MYSQL_PORT,
                    user=settings.MYSQL_USER,
                    password=settings.MYSQL_PASSWORD,
                    database=settings.MYSQL_DATABASE,
                )
                logger.info("Local MySQL connection pool established successfully (URBANPULSE_ENV='local').")
            except Exception as e:
                logger.error(f"Failed to create MySQL connection pool: {e}")
                raise
    return _connection_pool


@contextmanager
def get_db_connection(use_database: bool = True):
    """
    Context manager yielding a database connection.
    If use_database is False, connects to server without selecting a DB.
    """
    if not use_database:
        if settings.is_cloud:
            target_host = settings.TIDB_HOST
            if not target_host or target_host in ("localhost", "127.0.0.1"):
                raise ValueError("URBANPULSE_ENV='cloud' prohibits connecting to localhost or using an empty host.")
            if not settings.TIDB_USER or not settings.TIDB_PASSWORD:
                raise ValueError("URBANPULSE_ENV='cloud' requires valid cloud database credentials (TIDB_USER, TIDB_PASSWORD).")
            conn = mysql.connector.connect(
                host=target_host,
                port=settings.TIDB_PORT,
                user=settings.TIDB_USER,
                password=settings.TIDB_PASSWORD,
                ssl_ca=certifi.where(),
                ssl_verify_cert=True,
                ssl_verify_identity=True,
            )
        else:
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


# ==========================================
# TiDB Cloud (TLS Encrypted) Connection Managers
# ==========================================

import certifi

_tidb_pool = None


def _get_ssl_options(host: str):
    """Returns TLS certificate configuration for remote connections such as TiDB Cloud."""
    if host in ("localhost", "127.0.0.1", "") or not host:
        return {}
    return {
        "ssl_ca": certifi.where(),
        "ssl_verify_cert": True,
    }


def get_tidb_pool():
    """Provides a connection pool for TiDB Cloud with verified TLS."""
    global _tidb_pool
    if _tidb_pool is None:
        if not settings.TIDB_HOST:
            raise ValueError(
                "TIDB_HOST is not configured. Please set TIDB_HOST, TIDB_USER, and TIDB_PASSWORD in environment."
            )
        try:
            pool_config = {
                "pool_name": "urbanpulse_tidb_pool",
                "pool_size": 5,
                "pool_reset_session": True,
                "host": settings.TIDB_HOST,
                "port": settings.TIDB_PORT,
                "user": settings.TIDB_USER,
                "password": settings.TIDB_PASSWORD,
                "database": settings.TIDB_DATABASE,
            }
            pool_config.update(_get_ssl_options(settings.TIDB_HOST))
            _tidb_pool = pooling.MySQLConnectionPool(**pool_config)
            logger.info("TiDB Cloud connection pool established successfully with TLS.")
        except Exception as e:
            logger.error(f"Failed to create TiDB Cloud connection pool: {e}")
            raise
    return _tidb_pool


@contextmanager
def get_tidb_connection(use_database: bool = True):
    """Context manager yielding an authenticated TiDB Cloud connection with TLS."""
    if not settings.TIDB_HOST:
        raise ValueError(
            "TIDB_HOST is not configured. Please set TIDB_HOST, TIDB_USER, and TIDB_PASSWORD in environment."
        )
    conn_params = {
        "host": settings.TIDB_HOST,
        "port": settings.TIDB_PORT,
        "user": settings.TIDB_USER,
        "password": settings.TIDB_PASSWORD,
    }
    if use_database:
        conn_params["database"] = settings.TIDB_DATABASE
    conn_params.update(_get_ssl_options(settings.TIDB_HOST))
    conn = mysql.connector.connect(**conn_params)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_tidb_cursor(commit: bool = False, dictionary: bool = True, use_database: bool = True):
    """Context manager yielding a cursor for TiDB Cloud queries."""
    with get_tidb_connection(use_database=use_database) as conn:
        cursor = conn.cursor(dictionary=dictionary, buffered=True)
        try:
            yield cursor
            if commit:
                conn.commit()
        except Exception as e:
            if commit:
                conn.rollback()
            logger.error(f"TiDB error during cursor execution: {e}")
            raise
        finally:
            cursor.close()
