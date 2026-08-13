import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from app.storage.paths import resolve_data_dir, resolve_override

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_DEFAULT_MODEL = os.getenv("OPENROUTER_DEFAULT_MODEL", "openrouter/free")
OPENROUTER_FALLBACK_MODEL = "google/gemini-2.5-flash"

# z.ai (Zhipu / BigModel, GLM) — OpenAI-compatible provider usable without VPN.
ZAI_API_KEY = os.getenv("ZAI_API_KEY", "")
ZAI_BASE_URL = os.getenv("ZAI_BASE_URL", "https://api.z.ai/api/paas/v4")

# Active provider selection: "openrouter" (default) or "zai".
# When unset, the factory defaults to openrouter (backward compat).
APP_PROVIDER = os.getenv("APP_PROVIDER", "").strip().lower()

# Data-root (ADR-0012 / ADR-0016): absolute directory outside the source tree
# for global app artifacts (app.db, prompt_logs/). Workspace folders are opened
# separately (user-folder + .catalog/index.db). Env override: APP_DATA_DIR.
# APP_WORKSPACE / APP_DB_PATH / PROMPT_LOG_DIR remain point-overrides for
# backward compat (e.g. tests pointing at tmp_path); when unset they resolve
# under the data-root instead of the process CWD.
_DATA_DIR = resolve_data_dir()
APP_WORKSPACE = str(resolve_override("APP_WORKSPACE", _DATA_DIR / "workspace"))
APP_DB_PATH = str(resolve_override("APP_DB_PATH", _DATA_DIR / "app.db"))
_fs_root_env = os.getenv("APP_FS_ROOT")
APP_FS_ROOT = str(
    Path(_fs_root_env).expanduser().resolve() if _fs_root_env else Path.home().resolve()
)

# Logging — root level for the ``app`` logger hierarchy (default INFO).
# Read once at import time so Settings carries a stable value.
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Prompt logging — raw request/response capture for quality analysis.
# Disabled by default; opt-in via PROMPT_LOG_ENABLED=1.
_TRUTHY = {"1", "true", "yes", "on"}
PROMPT_LOG_ENABLED = os.getenv("PROMPT_LOG_ENABLED", "").strip().lower() in _TRUTHY
PROMPT_LOG_DIR = str(resolve_override("PROMPT_LOG_DIR", _DATA_DIR / "prompt_logs"))


@dataclass(frozen=True)
class Settings:
    """Application settings assembled from environment variables.

    Carried on ``app.state.settings`` and consumed by the lifespan and the
    API routers (step 06). Frozen so it cannot be mutated after startup.
    """

    db_path: str = APP_DB_PATH
    workspace_dir: str = APP_WORKSPACE
    fs_root: str = APP_FS_ROOT
    api_key: str = OPENROUTER_API_KEY
    base_url: str = OPENROUTER_BASE_URL
    default_model: str = OPENROUTER_DEFAULT_MODEL
    zai_api_key: str = ZAI_API_KEY
    zai_base_url: str = ZAI_BASE_URL
    app_provider: str = APP_PROVIDER
    prompt_log_enabled: bool = PROMPT_LOG_ENABLED
    prompt_log_dir: str = PROMPT_LOG_DIR
    log_level: str = LOG_LEVEL


def get_settings() -> Settings:
    """Build a :class:`Settings` from the current environment.

    Re-resolves the data-root and its derived paths (workspace/db/prompt-log)
    on every call — unlike the module-level constants above, which are frozen
    at import time — so tests can ``monkeypatch.setenv`` and immediately see
    the effect without re-importing :mod:`app.config`.
    """
    data_dir = resolve_data_dir()
    workspace_dir = resolve_override("APP_WORKSPACE", data_dir / "workspace")
    db_path = resolve_override("APP_DB_PATH", data_dir / "app.db")
    prompt_log_dir = resolve_override("PROMPT_LOG_DIR", data_dir / "prompt_logs")
    fs_root_env = os.getenv("APP_FS_ROOT")
    fs_root = (
        Path(fs_root_env).expanduser().resolve()
        if fs_root_env
        else Path.home().resolve()
    )
    return Settings(
        db_path=str(db_path),
        workspace_dir=str(workspace_dir),
        fs_root=str(fs_root),
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        default_model=OPENROUTER_DEFAULT_MODEL,
        zai_api_key=ZAI_API_KEY,
        zai_base_url=ZAI_BASE_URL,
        app_provider=APP_PROVIDER,
        prompt_log_enabled=PROMPT_LOG_ENABLED,
        prompt_log_dir=str(prompt_log_dir),
        log_level=LOG_LEVEL,
    )
