from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from catalog.config import key_managed_by_env, resolve_provider_keys
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


def test_key_managed_by_env_reads_os_getenv(monkeypatch) -> None:
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    assert key_managed_by_env("ZAI_API_KEY") is False
    monkeypatch.setenv("ZAI_API_KEY", "  env-secret  ")
    assert key_managed_by_env("ZAI_API_KEY") is True
    monkeypatch.setenv("ZAI_API_KEY", "   ")
    assert key_managed_by_env("ZAI_API_KEY") is False


def test_api_keys_roundtrip_in_app_db() -> None:
    db = Database(":memory:")
    db.init_schema(APP_SCHEMA, APP_USER_VERSION, migrations=APP_ADDITIVE_MIGRATIONS)
    assert get_api_keys(db) == ("", "")
    set_api_keys(db, openrouter_api_key="secret-or", zai_api_key="secret-zai")
    assert get_api_keys(db) == ("secret-or", "secret-zai")


def test_coerce_model_for_provider_styles() -> None:
    from catalog.llm.zai import DEFAULT_ZAI_MODEL
    from catalog.runtime import coerce_model_for_provider

    assert coerce_model_for_provider("zai", "openrouter/free", "test/model") == DEFAULT_ZAI_MODEL
    assert coerce_model_for_provider("openrouter", "glm-5.2", "test/model") == "test/model"
    assert coerce_model_for_provider("zai", "glm-4.6", "test/model") == "glm-4.6"
    assert coerce_model_for_provider("openrouter", "google/gem", "test/model") == "google/gem"


def test_apply_runtime_providers_resets_model_on_fallback(client, monkeypatch) -> None:
    from catalog.config import with_resolved_keys
    from catalog.runtime import apply_runtime_providers

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    set_api_keys(
        client.app.state.app_db,
        openrouter_api_key="or-key",
        zai_api_key="zai-key",
    )
    settings = with_resolved_keys(
        client.app.state.settings,
        persisted_openrouter="or-key",
        persisted_zai="zai-key",
    )
    apply_runtime_providers(client.app, settings)
    assert "zai" in client.app.state.providers
    client.app.state.active_provider = "zai"
    client.app.state.provider = client.app.state.providers["zai"]
    client.app.state.active_model = "glm-4.6"

    set_api_keys(client.app.state.app_db, openrouter_api_key="or-key", zai_api_key="")
    settings = with_resolved_keys(
        client.app.state.settings,
        persisted_openrouter="or-key",
        persisted_zai="",
    )
    apply_runtime_providers(client.app, settings)
    assert client.app.state.active_provider == "openrouter"
    assert "zai" not in client.app.state.providers
    assert client.app.state.active_model == "test/model"


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
    for item in body["providers"]:
        assert "new-secret-key" not in item.values()


def test_setup_lists_all_known_providers_when_only_one_configured(
    client, monkeypatch
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    client.app.state.settings = replace(
        client.app.state.settings, api_key="test-key", zai_api_key=""
    )
    body = client.get("/setup").json()
    by_id = {item["id"]: item for item in body["providers"]}
    assert set(by_id) == {"openrouter", "zai"}
    assert by_id["openrouter"]["configured"] is True
    assert by_id["zai"]["configured"] is False
    assert by_id["openrouter"]["name"] == "OpenRouter"
    assert by_id["zai"]["name"] == "z.ai"
    assert body["keys_configured"] is True
    assert body["provider"]
    assert body["openrouter_configured"] is True
    assert body["zai_configured"] is False
    assert by_id[client.app.state.active_provider]["active"] is True
    assert sum(1 for item in body["providers"] if item["active"]) == 1


def test_setup_providers_without_runtime_settings(client, monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    set_api_keys(
        client.app.state.app_db,
        openrouter_api_key="db-or",
        zai_api_key="",
    )
    del client.app.state.settings
    body = client.get("/setup").json()
    by_id = {item["id"]: item for item in body["providers"]}
    assert set(by_id) == {"openrouter", "zai"}
    assert by_id["openrouter"]["configured"] is True
    assert by_id["zai"]["configured"] is False
    assert by_id[body["provider"]]["active"] is True
    assert body["keys_configured"] is True
    assert body["openrouter_configured"] is True
    assert body["zai_configured"] is False


def test_setup_managed_by_env_ignores_persisted_value(client, monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("ZAI_API_KEY", "env-zai-secret")
    set_api_keys(
        client.app.state.app_db,
        openrouter_api_key="db-or",
        zai_api_key="db-zai",
    )
    body = client.get("/setup").json()
    zai = next(item for item in body["providers"] if item["id"] == "zai")
    assert zai["managed_by_env"] is True
    assert "env-zai-secret" not in str(body)
    assert "db-zai" not in str(body)
    openrouter = next(item for item in body["providers"] if item["id"] == "openrouter")
    assert openrouter["managed_by_env"] is False


def test_put_setup_keys_partial_keeps_other_key_and_exposes_zai(
    client, monkeypatch
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    set_api_keys(
        client.app.state.app_db,
        openrouter_api_key="keep-or",
        zai_api_key="",
    )
    client.app.state.settings = replace(
        client.app.state.settings, api_key="keep-or", zai_api_key=""
    )

    resp = client.put("/setup/keys", json={"zai_api_key": "new-zai"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert get_api_keys(client.app.state.app_db) == ("keep-or", "new-zai")
    by_id = {item["id"]: item for item in body["providers"]}
    assert by_id["openrouter"]["configured"] is True
    assert by_id["zai"]["configured"] is True
    assert "keep-or" not in resp.text
    assert "new-zai" not in resp.text

    providers = client.get("/providers").json()
    assert any(item["id"] == "zai" for item in providers)
    assert "zai" in client.app.state.providers


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
