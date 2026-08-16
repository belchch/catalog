import os
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv

from catalog.storage.paths import resolve_data_dir, resolve_override

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_DEFAULT_MODEL = os.getenv("OPENROUTER_DEFAULT_MODEL", "openrouter/free")
OPENROUTER_FALLBACK_MODEL = "google/gemini-2.5-flash"

ZAI_API_KEY = os.getenv("ZAI_API_KEY", "")
ZAI_BASE_URL = os.getenv("ZAI_BASE_URL", "https://api.z.ai/api/paas/v4")

APP_PROVIDER = os.getenv("APP_PROVIDER", "").strip().lower()

_DATA_DIR = resolve_data_dir()
APP_WORKSPACE = str(resolve_override("APP_WORKSPACE", _DATA_DIR / "workspace"))
APP_DB_PATH = str(resolve_override("APP_DB_PATH", _DATA_DIR / "app.db"))
_fs_root_env = os.getenv("APP_FS_ROOT")
APP_FS_ROOT = str(
    Path(_fs_root_env).expanduser().resolve() if _fs_root_env else Path.home().resolve()
)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

_TRUTHY = {"1", "true", "yes", "on"}
PROMPT_LOG_ENABLED = os.getenv("PROMPT_LOG_ENABLED", "").strip().lower() in _TRUTHY
PROMPT_LOG_DIR = str(resolve_override("PROMPT_LOG_DIR", _DATA_DIR / "prompt_logs"))


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= minimum else default


@dataclass(frozen=True)
class Settings:
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
    max_skill_depth: int = 2


def resolve_provider_keys(
    *,
    persisted_openrouter: str = "",
    persisted_zai: str = "",
) -> tuple[str, str]:
    env_or = os.getenv("OPENROUTER_API_KEY", "").strip()
    env_zai = os.getenv("ZAI_API_KEY", "").strip()
    return (
        env_or or persisted_openrouter.strip(),
        env_zai or persisted_zai.strip(),
    )


def key_managed_by_env(env_var: str) -> bool:
    return bool(os.getenv(env_var, "").strip())



def keys_are_configured(settings: Settings) -> bool:
    return bool(settings.api_key.strip() or settings.zai_api_key.strip())


def with_resolved_keys(
    settings: Settings,
    *,
    persisted_openrouter: str = "",
    persisted_zai: str = "",
) -> Settings:
    api_key, zai_api_key = resolve_provider_keys(
        persisted_openrouter=persisted_openrouter,
        persisted_zai=persisted_zai,
    )
    return replace(settings, api_key=api_key, zai_api_key=zai_api_key)


def get_settings() -> Settings:
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
    api_key, zai_api_key = resolve_provider_keys()
    return Settings(
        db_path=str(db_path),
        workspace_dir=str(workspace_dir),
        fs_root=str(fs_root),
        api_key=api_key,
        base_url=os.getenv("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL),
        default_model=os.getenv("OPENROUTER_DEFAULT_MODEL", OPENROUTER_DEFAULT_MODEL),
        zai_api_key=zai_api_key,
        zai_base_url=os.getenv("ZAI_BASE_URL", ZAI_BASE_URL),
        app_provider=os.getenv("APP_PROVIDER", "").strip().lower(),
        prompt_log_enabled=os.getenv("PROMPT_LOG_ENABLED", "").strip().lower() in _TRUTHY,
        prompt_log_dir=str(prompt_log_dir),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        max_skill_depth=_env_int("APP_MAX_SKILL_DEPTH", 2),
    )
