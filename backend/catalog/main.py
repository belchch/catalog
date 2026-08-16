from __future__ import annotations

import os
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from catalog.api import checks, documents, models, runs, sessions, skills, workspaces
from catalog.config import get_settings, with_resolved_keys
from catalog.llm.factory import build_providers, select_provider
from catalog.llm.openrouter import build_debug_hooks
from catalog.logging_config import setup_logging
from catalog.runtime import coerce_model_for_provider
from catalog.storage.db import Database
from catalog.storage.repo_app_settings import (
    get_api_keys,
    get_app_settings,
    set_app_settings,
)
from catalog.storage.schema import (
    APP_ADDITIVE_MIGRATIONS,
    APP_SCHEMA,
    APP_USER_VERSION,
)
from catalog.storage.workspace import WorkspaceManager

setup_logging(level=get_settings().log_level)


def package_static_dir() -> Path | None:
    packaged = Path(__file__).resolve().parent / "static"
    if packaged.is_dir() and (packaged / "index.html").is_file():
        return packaged
    try:
        root = files("catalog").joinpath("static")
    except (TypeError, ModuleNotFoundError, FileNotFoundError):
        return None
    if hasattr(root, "is_dir") and root.is_dir():
        index = root.joinpath("index.html")
        if hasattr(index, "is_file") and index.is_file():
            return Path(str(root))
    return None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    app_db = Database(settings.db_path)
    app_db.init_schema(APP_SCHEMA, APP_USER_VERSION, migrations=APP_ADDITIVE_MIGRATIONS)
    persisted_or, persisted_zai = get_api_keys(app_db)
    settings = with_resolved_keys(
        settings,
        persisted_openrouter=persisted_or,
        persisted_zai=persisted_zai,
    )
    http_client = httpx.AsyncClient(timeout=60.0, event_hooks=build_debug_hooks())
    app.state.app_db = app_db
    app.state.http_client = http_client
    providers = build_providers(settings, http_client)
    app.state.providers = providers
    selected = select_provider(providers, settings.app_provider)
    app.state.provider = selected
    active_name = next(
        (name for name, inst in providers.items() if inst is selected),
        next(iter(providers), "openrouter"),
    )
    stored_provider, stored_model = get_app_settings(app_db)
    if stored_provider and stored_provider in providers:
        app.state.active_provider = stored_provider
        app.state.provider = providers[stored_provider]
        active_name = stored_provider
    else:
        app.state.active_provider = active_name
        if stored_provider:
            stored_model = ""
    app.state.active_model = coerce_model_for_provider(
        active_name,
        stored_model,
        settings.default_model,
    )
    if not stored_provider and not stored_model:
        set_app_settings(app_db, provider=active_name, model=app.state.active_model)
    app.state.active_planner_turns = 0
    manager = WorkspaceManager()
    manager.bind(app_db=app_db, app_state=app.state)
    manager.set_busy_probe(lambda: app.state.active_planner_turns > 0)
    app.state.workspace_manager = manager
    app.state.settings = settings
    try:
        yield
    finally:
        await http_client.aclose()


app = FastAPI(title="Catalog API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(sessions.router)
app.include_router(skills.router)
app.include_router(runs.router)
app.include_router(models.router)
app.include_router(workspaces.router)
app.include_router(checks.router)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPO_GIT_SHA: str | None = None


def _resolve_git_sha() -> str:
    env = os.getenv("GIT_SHA", "").strip()
    if env and env != "unknown":
        return env
    global _REPO_GIT_SHA
    if _REPO_GIT_SHA is None:
        try:
            out = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=_REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            )
            _REPO_GIT_SHA = out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            _REPO_GIT_SHA = ""
    return _REPO_GIT_SHA


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "git_sha": _resolve_git_sha()}


_STATIC = package_static_dir()
if _STATIC is not None:
    app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="spa")
