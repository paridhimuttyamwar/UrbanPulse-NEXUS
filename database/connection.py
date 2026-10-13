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
                    "pool_reset_session": False,
                    "use_pure": True,
                    "connection_timeout": 15,
                    "read_timeout": 15,
                    "write_timeout": 15,
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
                    connection_timeout=15,
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
    Context manager yielding an authenticated database connection.
    In cloud mode (TiDB Cloud): creates a direct pure-Python connection with verified TLS,
    finite socket read/write/connect timeouts (15s), and clean disconnection, avoiding pool-specific hangs.
    In local mode: connects to local MySQL (using connection pool for DB queries).
    """
    if settings.is_cloud:
        target_host = settings.TIDB_HOST
        if not target_host or target_host in ("localhost", "127.0.0.1"):
            raise ValueError("URBANPULSE_ENV='cloud' prohibits connecting to localhost or using an empty host.")
        if not settings.TIDB_USER or not settings.TIDB_PASSWORD:
            raise ValueError("URBANPULSE_ENV='cloud' requires valid cloud database credentials (TIDB_USER, TIDB_PASSWORD).")

        if not use_database:
            conn_params = {
                "host": target_host,
                "port": settings.TIDB_PORT,
                "user": settings.TIDB_USER,
                "password": settings.TIDB_PASSWORD,
                "use_pure": True,
                "connection_timeout": 15,
                "read_timeout": 15,
                "write_timeout": 15,
                "ssl_ca": certifi.where(),
                "ssl_verify_cert": True,
                "ssl_verify_identity": True,
            }
            conn = mysql.connector.connect(**conn_params)
            try:
                yield conn
            finally:
                try:
                    conn.close()
                except Exception as close_err:
                    logger.debug(f"Error closing direct TiDB connection: {close_err}")
        else:
            pool = get_db_pool()
            conn = pool.get_connection()
            try:
                yield conn
            finally:
                try:
                    conn.close()
                except Exception as close_err:
                    logger.debug(f"Error returning connection to pool: {close_err}")
    else:
        # Local Mode: connects to local MySQL without SSL
        if not use_database:
            conn = mysql.connector.connect(
                host=settings.MYSQL_HOST,
                port=settings.MYSQL_PORT,
                user=settings.MYSQL_USER,
                password=settings.MYSQL_PASSWORD,
                connection_timeout=15,
            )
            try:
                yield conn
            finally:
                try:
                    conn.close()
                except Exception as close_err:
                    logger.debug(f"Error closing unpooled connection: {close_err}")
        else:
            pool = get_db_pool()
            conn = pool.get_connection()
            try:
                yield conn
            finally:
                try:
                    conn.close()
                except Exception as close_err:
                    logger.debug(f"Error returning connection to pool: {close_err}")


@contextmanager
def get_db_cursor(commit: bool = False, dictionary: bool = True):
    """
    Context manager yielding a cursor and handling commit/rollback.
    """
    with get_db_connection() as conn:
        cursor = None
        try:
            cursor = conn.cursor(dictionary=dictionary, buffered=True)
            yield cursor
            if commit:
                conn.commit()
        except Exception as e:
            if commit:
                try:
                    conn.rollback()
                except Exception as rb_err:
                    logger.warning(f"Failed to rollback transaction: {rb_err}")
            logger.error(f"Database error during cursor execution: {e}")
            raise
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception as c_err:
                    logger.debug(f"Error closing cursor: {c_err}")


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
                "pool_reset_session": False,
                "use_pure": True,
                "connection_timeout": 15,
                "read_timeout": 15,
                "write_timeout": 15,
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
        "use_pure": True,
        "connection_timeout": 15,
        "read_timeout": 15,
        "write_timeout": 15,
    }
    if use_database:
        conn_params["database"] = settings.TIDB_DATABASE
    conn_params.update(_get_ssl_options(settings.TIDB_HOST))
    conn = mysql.connector.connect(**conn_params)
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception as close_err:
            logger.debug(f"Error closing TiDB connection: {close_err}")


@contextmanager
def get_tidb_cursor(commit: bool = False, dictionary: bool = True, use_database: bool = True):
    """Context manager yielding a cursor for TiDB Cloud queries."""
    with get_tidb_connection(use_database=use_database) as conn:
        cursor = None
        try:
            cursor = conn.cursor(dictionary=dictionary, buffered=True)
            yield cursor
            if commit:
                conn.commit()
        except Exception as e:
            if commit:
                try:
                    conn.rollback()
                except Exception as rb_err:
                    logger.warning(f"Failed to rollback TiDB transaction: {rb_err}")
            logger.error(f"TiDB error during cursor execution: {e}")
            raise
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception as c_err:
                    logger.debug(f"Error closing TiDB cursor: {c_err}")


def close_all_pools():
    """
    Resets any active database connection pools.
    Useful for clean process teardown and test isolation.
    """
    global _connection_pool, _tidb_pool
    _connection_pool = None
    _tidb_pool = None


import atexit
atexit.register(close_all_pools)


