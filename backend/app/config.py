import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_DEFAULT_MODEL = os.getenv("OPENROUTER_DEFAULT_MODEL", "openrouter/free")
OPENROUTER_FALLBACK_MODEL = "google/gemini-2.5-flash"

APP_WORKSPACE = os.getenv("APP_WORKSPACE", "workspace")
APP_DB_PATH = os.getenv("APP_DB_PATH", "catalog.db")


@dataclass(frozen=True)
class Settings:
    """Application settings assembled from environment variables.

    Carried on ``app.state.settings`` and consumed by the lifespan and the
    API routers (step 06). Frozen so it cannot be mutated after startup.
    """

    db_path: str = APP_DB_PATH
    workspace_dir: str = APP_WORKSPACE
    api_key: str = OPENROUTER_API_KEY
    base_url: str = OPENROUTER_BASE_URL
    default_model: str = OPENROUTER_DEFAULT_MODEL


def get_settings() -> Settings:
    """Build a :class:`Settings` from the current environment."""
    return Settings()
