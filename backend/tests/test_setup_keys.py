from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from catalog.config import resolve_provider_keys
from catalog.main import package_static_dir
from catalog.storage.db import Database
from catalog.storage.repo_app_settings import get_api_keys, set_api_keys
from catalog.storage.schema import (
    APP_ADDITIVE_MIGRATIONS,
    APP_SCHEMA,
    APP_USER_VERSION,
)


def test_resolve_provider_keys_env_overrides_persisted(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-or")
    monkeypatch.setenv("ZAI_API_KEY", "env-zai")
    assert resolve_provider_keys(
        persisted_openrouter="db-or",
        persisted_zai="db-zai",
    ) == ("env-or", "env-zai")


def test_resolve_provider_keys_falls_back_to_persisted(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    assert resolve_provider_keys(
        persisted_openrouter="db-or",
        persisted_zai="db-zai",
    ) == ("db-or", "db-zai")


def test_api_keys_roundtrip_in_app_db() -> None:
    db = Database(":memory:")
    db.init_schema(APP_SCHEMA, APP_USER_VERSION, migrations=APP_ADDITIVE_MIGRATIONS)
    assert get_api_keys(db) == ("", "")
    set_api_keys(db, openrouter_api_key="secret-or", zai_api_key="secret-zai")
    assert get_api_keys(db) == ("secret-or", "secret-zai")


def test_setup_endpoints_hide_secrets(client, monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    set_api_keys(client.app.state.app_db, openrouter_api_key="", zai_api_key="")
    client.app.state.settings = replace(
        client.app.state.settings, api_key="", zai_api_key=""
    )

    before = client.get("/setup").json()
    assert before["keys_configured"] is False
    assert "api_key" not in before
    assert "openrouter_api_key" not in before

    resp = client.put(
        "/setup/keys",
        json={"openrouter_api_key": "new-secret-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["keys_configured"] is True
    assert body["openrouter_configured"] is True
    assert "new-secret-key" not in resp.text

    settings = client.get("/settings").json()
    assert settings["keys_configured"] is True
    assert "new-secret-key" not in settings.values()


def test_package_static_dir_points_inside_package() -> None:
    static = Path(__file__).resolve().parents[1] / "catalog" / "static"
    static.mkdir(parents=True, exist_ok=True)
    marker = static / "index.html"
    created = not marker.exists()
    if created:
        marker.write_text("<html></html>", encoding="utf-8")
    try:
        resolved = package_static_dir()
        assert resolved is not None
        assert resolved == static.resolve()
        assert "catalog" in resolved.parts
        assert resolved.name == "static"
    finally:
        if created:
            marker.unlink(missing_ok=True)
            try:
                static.rmdir()
            except OSError:
                pass


def test_package_static_dir_ignores_empty_dir() -> None:
    static = Path(__file__).resolve().parents[1] / "catalog" / "static"
    if static.is_dir() and not (static / "index.html").is_file():
        assert package_static_dir() is None
