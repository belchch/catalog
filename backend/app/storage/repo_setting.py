"""Repository for ``app_setting`` — small persisted key/value config.

Used by the KB-repo connection (ADR-0022): the path/remote/push-enabled
choice a user makes in the UI must survive a process restart, so it is
written here rather than kept only in ``app.state``.
"""

from __future__ import annotations

from app.storage.db import Database


def get_setting(db: Database, key: str) -> str | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT value FROM app_setting WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row is not None else None


def set_setting(db: Database, key: str, value: str) -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO app_setting(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
