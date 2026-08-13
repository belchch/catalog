"""Catalog API application (FastAPI).

Wires the engine (step 03), storage (04) and skills (05) into the HTTP /
WebSocket routers (06). The lifespan boots the global app SQLite database, a
workspace manager (no folder open at start), a shared ``httpx`` client and the
LLM provider factory — all carried on ``app.state`` so the routers (and tests)
read their collaborators from one place.

The factory (:func:`app.llm.factory.build_providers`) instantiates every
configured provider (OpenRouter always; z.ai when ``ZAI_API_KEY`` is set) and
:func:`select_provider` picks the active one via ``APP_PROVIDER``. Both the
dict (``app.state.providers``) and the active instance (``app.state.provider``)
are exposed.

Tests do not construct these collaborators manually: they enter the
``TestClient`` lifespan context (which runs this lifespan over test-scoped
paths via a patched ``get_settings``) and then override only
``app.state.provider`` with a fake (see ``tests/conftest.py``).
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import documents, models, runs, sessions, skills
from app.config import Settings, get_settings
from app.llm.factory import build_providers, select_provider
from app.llm.openrouter import build_debug_hooks
from app.llm.zai import DEFAULT_ZAI_MODEL
from app.logging_config import setup_logging
from app.storage.db import Database
from app.storage.repo_app_settings import get_app_settings, set_app_settings
from app.storage.schema import APP_SCHEMA, APP_USER_VERSION
from app.storage.workspace import WorkspaceManager

setup_logging(level=get_settings().log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = get_settings()
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    app_db = Database(settings.db_path)
    app_db.init_schema(APP_SCHEMA, APP_USER_VERSION, migrations=[])
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
    app.state.active_provider = active_name
    default_model = settings.default_model
    if active_name == "zai" and ("/" in default_model or not default_model):
        default_model = DEFAULT_ZAI_MODEL
    app.state.active_model = default_model
    stored_provider, stored_model = get_app_settings(app_db)
    if stored_provider or stored_model:
        if stored_provider and stored_provider in providers:
            app.state.active_provider = stored_provider
            app.state.provider = providers[stored_provider]
        if stored_model:
            app.state.active_model = stored_model
    else:
        set_app_settings(app_db, provider=active_name, model=default_model)
    manager = WorkspaceManager()
    manager.bind(app_db=app_db, app_state=app.state)
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


_STATIC = Path(__file__).resolve().parent.parent / "static"
if _STATIC.is_dir():
    app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="spa")
