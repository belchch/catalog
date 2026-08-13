from __future__ import annotations

from app.storage.db import Database


def get_app_settings(db: Database) -> tuple[str, str]:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT provider, model FROM app_settings WHERE id = 1"
        ).fetchone()
    if row is None:
        return "", ""
    return str(row["provider"] or ""), str(row["model"] or "")


def set_app_settings(
    db: Database,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[str, str]:
    current_provider, current_model = get_app_settings(db)
    next_provider = current_provider if provider is None else provider
    next_model = current_model if model is None else model
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO app_settings(id, provider, model) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET provider = excluded.provider, model = excluded.model",
            (next_provider, next_model),
        )
    return next_provider, next_model
