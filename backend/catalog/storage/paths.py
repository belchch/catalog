"""Data-root resolution (ADR-0012).

Centralizes the logic for turning ``APP_DATA_DIR`` (and the point overrides
``APP_WORKSPACE`` / ``APP_DB_PATH`` / ``PROMPT_LOG_DIR``) into absolute paths.
Reads ``os.environ`` directly on every call (no caching) so callers — notably
:func:`catalog.config.get_settings` — pick up ``monkeypatch.setenv`` changes
without a re-import.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_APP_NAME = "catalog"


def os_default_data_dir() -> Path:
    """OS-appropriate default data directory, unresolved (no env, no I/O)."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _APP_NAME
    return Path.home() / ".local" / "share" / _APP_NAME


def resolve_data_dir() -> Path:
    """Resolve the data-root: ``APP_DATA_DIR`` env override, else the OS default.

    Always an absolute path (``expanduser`` + ``resolve``); never touches disk.
    """
    override = os.getenv("APP_DATA_DIR")
    base = Path(override) if override else os_default_data_dir()
    return base.expanduser().resolve()


def resolve_override(env_var: str, default: Path) -> Path:
    """Read ``env_var``; fall back to ``default`` when unset. Always absolute."""
    override = os.getenv(env_var)
    path = Path(override) if override else default
    return path.expanduser().resolve()
