"""Catalog API application (FastAPI).

Wires the engine (step 03), storage (04) and skills (05) into the HTTP /
WebSocket routers (06). The lifespan boots the SQLite database, a shared
``httpx`` client and the OpenRouter provider, and builds the base document
tool registry — all carried on ``app.state`` so the routers (and tests) read
their collaborators from one place.

Tests do not construct these collaborators manually: they enter the
``TestClient`` lifespan context (which runs this lifespan over test-scoped
paths via a patched ``get_settings``) and then override only
``app.state.provider`` with a fake (see ``tests/conftest.py``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import documents, runs, sessions, skills
from app.config import Settings, get_settings
from app.documents.tools import build_document_tools
from app.llm.openrouter import OpenRouterProvider, build_debug_hooks
from app.storage.db import Database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = get_settings()
    db = Database(settings.db_path)
    db.init_schema()
    http_client = httpx.AsyncClient(timeout=60.0, event_hooks=build_debug_hooks())
    app.state.db = db
    app.state.http_client = http_client
    app.state.provider = OpenRouterProvider(
        http_client, settings.api_key, settings.base_url
    )
    app.state.workspace = settings.workspace_dir
    app.state.tools = build_document_tools(db, settings.workspace_dir)
    app.state.settings = settings
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
