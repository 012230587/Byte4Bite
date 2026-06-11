"""
MySQL connection helper for Byte4Bite.

Reads credentials from Backend/.env:
  MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE

Data flow: API services -> get_connection() -> recipe_repository / retriever queries.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

try:
    import mysql.connector
    from mysql.connector import pooling
except ImportError:  # pragma: no cover
    mysql = None
    pooling = None

_POOL: Optional["pooling.MySQLConnectionPool"] = None

_POOL_CONFIG = {
    "pool_name": "byte4bite_pool",
    "pool_size": 5,
    "pool_reset_session": True,
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "byte4bite"),
    "charset": "utf8mb4",
    "collation": "utf8mb4_unicode_ci",
    "autocommit": False,
}


def _get_pool() -> "pooling.MySQLConnectionPool":
    """Lazy-init a connection pool (one pool per process)."""
    global _POOL
    if _POOL is None:
        if pooling is None:
            raise RuntimeError(
                "mysql-connector-python is not installed. Run: pip install mysql-connector-python"
            )
        _POOL = pooling.MySQLConnectionPool(**_POOL_CONFIG)
    return _POOL


@contextmanager
def get_connection() -> Generator:
    """
    Context manager yielding a pooled MySQL connection.
    Commits on success, rolls back on exception.
    """
    pool = _get_pool()
    conn = pool.get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ping_database() -> bool:
    """Health-check used at FastAPI startup."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
        return True
    except Exception as exc:
        print(f"DEBUG: MySQL ping failed: {exc}")
        return False
