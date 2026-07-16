from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from app.storage.schema import ADDITIVE_MIGRATIONS, SCHEMA_SQL


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
        """Create all tables (idempotent) and apply additive migrations.

        ``CREATE TABLE IF NOT EXISTS`` only covers fresh databases; columns
        added after the initial release are applied via guarded
        ``ALTER TABLE`` (see ``ADDITIVE_MIGRATIONS``). Each ALTER is wrapped so
        a "duplicate column" error on an already-migrated database is treated
        as success.
        """
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
            for _table, _column, ddl in ADDITIVE_MIGRATIONS:
                try:
                    conn.execute(ddl)
                except sqlite3.OperationalError as exc:
                    # SQLite raises "duplicate column name" when the column
                    # already exists — that is the idempotent success case.
                    if "duplicate column" not in str(exc).lower():
                        raise

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
