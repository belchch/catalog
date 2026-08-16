from __future__ import annotations

from catalog.storage.db import Database


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


def get_api_keys(db: Database) -> tuple[str, str]:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT openrouter_api_key, zai_api_key FROM app_settings WHERE id = 1"
        ).fetchone()
    if row is None:
        return "", ""
    return str(row["openrouter_api_key"] or ""), str(row["zai_api_key"] or "")


def set_api_keys(
    db: Database,
    *,
    openrouter_api_key: str | None = None,
    zai_api_key: str | None = None,
) -> tuple[str, str]:
    current_or, current_zai = get_api_keys(db)
    next_or = current_or if openrouter_api_key is None else openrouter_api_key
    next_zai = current_zai if zai_api_key is None else zai_api_key
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO app_settings(id, openrouter_api_key, zai_api_key) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "openrouter_api_key = excluded.openrouter_api_key, "
            "zai_api_key = excluded.zai_api_key",
            (next_or, next_zai),
        )
    return next_or, next_zai


def get_skill_budget_limits(db: Database) -> tuple[int, int]:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT skill_budget_llm_calls, skill_budget_nested_runs "
            "FROM app_settings WHERE id = 1"
        ).fetchone()
    if row is None:
        return 60, 20
    llm = row["skill_budget_llm_calls"]
    runs = row["skill_budget_nested_runs"]
    return (
        60 if llm is None else int(llm),
        20 if runs is None else int(runs),
    )


def set_skill_budget_limits(
    db: Database,
    *,
    llm_calls: int | None = None,
    nested_runs: int | None = None,
) -> tuple[int, int]:
    current_llm, current_runs = get_skill_budget_limits(db)
    next_llm = current_llm if llm_calls is None else llm_calls
    next_runs = current_runs if nested_runs is None else nested_runs
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO app_settings(id, skill_budget_llm_calls, skill_budget_nested_runs) "
            "VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "skill_budget_llm_calls = excluded.skill_budget_llm_calls, "
            "skill_budget_nested_runs = excluded.skill_budget_nested_runs",
            (next_llm, next_runs),
        )
    return next_llm, next_runs
