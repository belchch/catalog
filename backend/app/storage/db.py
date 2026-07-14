from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from app.storage.schema import SCHEMA_SQL


class Database:
    """Thin wrapper around a SQLite database file.

    For on-disk databases a fresh connection is opened per operation: the slice
    is single-process, so no connection pooling or WAL is required. For
    in-memory databases (used in tests) a single shared connection is kept alive
    for the lifetime of this object, because a ``:memory:`` database is destroyed
    when its last connection closes.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._mem_conn: sqlite3.Connection | None = None
        if path == ":memory:":
            self._mem_conn = sqlite3.connect(path)
            self._mem_conn.row_factory = sqlite3.Row

    def init_schema(self) -> None:
        """Create all tables (idempotent)."""
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection with ``row_factory = sqlite3.Row``.

        The transaction is committed on normal exit and rolled back on error.
        """
        if self._mem_conn is not None:
            try:
                yield self._mem_conn
                self._mem_conn.commit()
            except Exception:
                self._mem_conn.rollback()
                raise
            return
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
