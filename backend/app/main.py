"""Catalog API application (FastAPI).

Wires the engine (step 03), storage (04) and skills (05) into the HTTP /
WebSocket routers (06). The lifespan boots the SQLite database, a shared
``httpx`` client and the LLM provider factory, and builds the base document
tool registry — all carried on ``app.state`` so the routers (and tests) read
their collaborators from one place.

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

from app.api import documents, kb, models, runs, sessions, skills
from app.config import Settings, get_settings
from app.documents.scan import scan_repo
from app.documents.tools import build_document_tools
from app.llm.factory import build_providers, select_provider
from app.llm.openrouter import build_debug_hooks
from app.llm.zai import DEFAULT_ZAI_MODEL
from app.logging_config import setup_logging
from app.skills.repo_skill import scan_skills
from app.storage.db import Database
from app.storage.git import ensure_repo
from app.storage.repo_setting import get_setting

_KB_REPO_SUBDIRS = ("documents", "results", "skills")

# Configure stdout logging at import time so every ``app.*`` log line carries
# the correlation context. Runs once when ``app.main`` is first imported
# (after uvicorn has set up its own loggers); idempotent on re-import.
setup_logging(level=get_settings().log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = get_settings()
    # ADR-0012/0022: data-root lives outside the source tree and may not exist
    # yet (fresh install / first run) — create it before anything reads/writes
    # under it.
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    db = Database(settings.db_path)
    db.init_schema()
    http_client = httpx.AsyncClient(timeout=60.0, event_hooks=build_debug_hooks())
    app.state.db = db
    app.state.http_client = http_client
    providers = build_providers(settings, http_client)
    app.state.providers = providers
    selected = select_provider(providers, settings.app_provider)
    app.state.provider = selected
    # CATALOG-14: mutable runtime selection of the active provider/model. Seeded
    # from env (frozen Settings); switchable at runtime via POST /settings. The
    # frozen Settings remain the source of API keys and the initial default.
    active_name = next(
        (name for name, inst in providers.items() if inst is selected),
        next(iter(providers), "openrouter"),
    )
    app.state.active_provider = active_name
    default_model = settings.default_model
    if active_name == "zai" and ("/" in default_model or not default_model):
        default_model = DEFAULT_ZAI_MODEL
    app.state.active_model = default_model

    # ADR-0022: one connected KB repo with documents/results/skills subfolders,
    # replacing the two app-owned repos. A prior POST /kb/connect persists its
    # path in app_setting and wins over the Settings default at every restart.
    repo_root = Path(get_setting(db, "kb_repo_path") or settings.workspace_dir)
    ensure_repo(repo_root)
    for subdir in _KB_REPO_SUBDIRS:
        (repo_root / subdir).mkdir(parents=True, exist_ok=True)
    app.state.repo_root = str(repo_root)
    app.state.workspace = str(repo_root)
    app.state.tools = build_document_tools(db, str(repo_root))
    app.state.settings = settings
    scan_repo(db, repo_root)
    scan_skills(db, repo_root)
    try:
        yield
    finally:
        await http_client.aclose()


app = FastAPI(title="Catalog API", version="0.1.0", lifespan=lifespan)

# CORS (step 01): the UI dev server runs on localhost:5173.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(sessions.router)
app.include_router(skills.router)
app.include_router(runs.router)
app.include_router(models.router)
app.include_router(kb.router)


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
