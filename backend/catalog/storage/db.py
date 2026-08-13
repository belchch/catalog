from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from catalog.storage.schema import (
    ADDITIVE_MIGRATIONS,
    WORKSPACE_SCHEMA,
    WORKSPACE_USER_VERSION,
)


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

    def init_schema(
        self,
        schema: str | None = None,
        user_version: int | None = None,
        migrations: list[tuple[str, str, str]] | None = None,
    ) -> None:
        sql = WORKSPACE_SCHEMA if schema is None else schema
        version = WORKSPACE_USER_VERSION if user_version is None else user_version
        migs = ADDITIVE_MIGRATIONS if migrations is None else migrations
        with self.connect() as conn:
            conn.executescript(sql)
            for _table, _column, ddl in migs:
                try:
                    conn.execute(ddl)
                except sqlite3.OperationalError as exc:
                    if "duplicate column" not in str(exc).lower():
                        raise
            conn.execute(f"PRAGMA user_version = {int(version)}")

    def user_version(self) -> int:
        with self.connect() as conn:
            row = conn.execute("PRAGMA user_version").fetchone()
        return int(row[0])

    def quick_check(self) -> str:
        with self.connect() as conn:
            row = conn.execute("PRAGMA quick_check").fetchone()
        return str(row[0])

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
