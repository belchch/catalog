"""Tests for the data-root resolution (ADR-0012, CATALOG-20).

Verifies that, absent explicit env overrides, ``get_settings()`` resolves
``workspace_dir`` / ``db_path`` / ``prompt_log_dir`` to absolute paths under
an OS/​``APP_DATA_DIR`` data-root — never under the process CWD or the source
tree — and that the point overrides (``APP_WORKSPACE`` / ``APP_DB_PATH`` /
``PROMPT_LOG_DIR``) still take precedence when set.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.config import get_settings
from app.storage.paths import os_default_data_dir, resolve_data_dir

_DATA_ROOT_ENV_VARS = ("APP_DATA_DIR", "APP_WORKSPACE", "APP_DB_PATH", "PROMPT_LOG_DIR")


@pytest.fixture(autouse=True)
def _clear_data_root_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate every test from whatever the local ``.env`` / shell happens to set."""
    for var in _DATA_ROOT_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_default_data_dir_is_absolute_and_os_specific() -> None:
    default = os_default_data_dir()
    assert default.is_absolute()
    assert default.name == "catalog"


def test_resolve_data_dir_defaults_outside_cwd() -> None:
    data_dir = resolve_data_dir()
    assert data_dir.is_absolute()
    assert data_dir == os_default_data_dir().expanduser().resolve()
    assert not str(data_dir).startswith(str(Path.cwd()))


def test_get_settings_defaults_are_absolute_under_data_root() -> None:
    settings = get_settings()
    data_dir = resolve_data_dir()

    for attr in ("workspace_dir", "db_path", "prompt_log_dir"):
        value = Path(getattr(settings, attr))
        assert value.is_absolute(), f"{attr} must be absolute, got {value}"

    assert Path(settings.workspace_dir) == data_dir / "workspace"
    assert Path(settings.db_path) == data_dir / "catalog.db"
    assert Path(settings.prompt_log_dir) == Path(settings.workspace_dir) / "prompt_logs"

    # Nothing lands in the source tree / process CWD by default.
    assert not str(settings.workspace_dir).startswith(str(Path.cwd()))
    assert not str(settings.db_path).startswith(str(Path.cwd()))


def test_app_data_dir_overrides_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))

    settings = get_settings()

    assert Path(settings.workspace_dir) == tmp_path / "workspace"
    assert Path(settings.db_path) == tmp_path / "catalog.db"
    assert Path(settings.prompt_log_dir) == tmp_path / "workspace" / "prompt_logs"


def test_point_overrides_still_win(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "unused-root"))
    monkeypatch.setenv("APP_WORKSPACE", str(tmp_path / "custom-ws"))
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "custom.db"))
    monkeypatch.setenv("PROMPT_LOG_DIR", str(tmp_path / "custom-logs"))

    settings = get_settings()

    assert Path(settings.workspace_dir) == tmp_path / "custom-ws"
    assert Path(settings.db_path) == tmp_path / "custom.db"
    assert Path(settings.prompt_log_dir) == tmp_path / "custom-logs"


def test_app_data_dir_expands_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_DATA_DIR", os.path.join("~", "catalog-data-root-test"))

    data_dir = resolve_data_dir()

    assert data_dir == Path.home() / "catalog-data-root-test"
