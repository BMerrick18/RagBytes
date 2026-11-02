"""Running totals of documents chunked and chunks returned.

Only these two numbers are kept. Nothing about the documents themselves is written down.
"""

import logging
import sqlite3
from contextlib import closing
from pathlib import Path

from shark_byte.config import settings
from shark_byte.schemas import StatsResponse

logger = logging.getLogger(__name__)

_SCHEMA = "CREATE TABLE IF NOT EXISTS totals (name TEXT PRIMARY KEY, value INTEGER NOT NULL)"
_ADD = "INSERT INTO totals (name, value) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET value = value + excluded.value"


def _connect() -> sqlite3.Connection:
    path = Path(settings.stats_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.execute(_SCHEMA)
    return connection


def record(chunks: int) -> None:
    """Count one more document and its chunks. A failure is logged, never raised to the caller."""
    try:
        with closing(_connect()) as connection, connection:
            connection.executemany(_ADD, [("documents", 1), ("chunks", chunks)])
    except sqlite3.Error:
        logger.exception("Could not update the usage totals")


def totals() -> StatsResponse:
    with closing(_connect()) as connection:
        values = dict(connection.execute("SELECT name, value FROM totals"))
    return StatsResponse(documents=values.get("documents", 0), chunks=values.get("chunks", 0))
