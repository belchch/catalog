"""Shared fixtures for the API tests (step 06).

WebSocket testing approach
--------------------------
We use Starlette's ``TestClient.websocket_connect`` — a synchronous context
manager backed by an in-process portal — so no extra dependency (such as
``httpx-ws``) is required. Both HTTP and WebSocket endpoints read their
collaborators from ``app.state``, which the lifespan populates. Tests enter
the ``TestClient`` lifespan context (running the real lifespan over
test-scoped paths via a patched ``get_settings``) and then override only
``app.state.provider`` with a :class:`FakeProvider`.

The database is file-backed (under ``tmp_path``) rather than ``:memory:``
because ``TestClient`` runs the ASGI app in a separate thread, and a single
in-memory SQLite connection cannot cross threads. A file database opens a
fresh connection per operation (see ``Database.connect``), which is
thread-safe; the ``db`` fixture opens that same file for direct seeding.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.llm.base import (
    CompletionResult,
    LLMProvider,
    Message,
    ModelInfo,
    StreamDelta,
    ToolSpec,
)
from app.main import app
from app.storage.db import Database


class FakeProvider:
    """Scripted provider: pops pre-set completions.

    Populate ``script`` with :class:`CompletionResult` items before driving a
    request; each ``complete`` call pops the next one. Exhausting the script
    raises :class:`AssertionError` so a miscounted test fails loudly instead of
    silently returning ``None``.
    """

    def __init__(self, script: list[CompletionResult] | None = None) -> None:
        self.script: list[CompletionResult] = list(script or [])
        self.requests: list[dict[str, Any]] = []

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        tool_choice: str = "auto",
        reasoning: str = "",
    ) -> CompletionResult:
        self.requests.append(
            {
                "model": model,
                "tools": [t.name for t in tools] if tools else None,
                "n_messages": len(messages),
                "reasoning": reasoning,
                "messages": messages,
            }
        )
        if not self.script:
            raise AssertionError("FakeProvider script exhausted")
        return self.script.pop(0)

    async def stream_complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        reasoning: str = "",
    ) -> Any:
        yield StreamDelta(content="")


# Static protocol check: FakeProvider satisfies LLMProvider.
_PROVIDER: LLMProvider = FakeProvider([])  # type: ignore[assignment]


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    """Test settings pointing at tmp_path (no repo pollution, no OS data-root)."""
    return Settings(
        db_path=str(tmp_path / "api.db"),
        workspace_dir=str(tmp_path / "ws"),
        prompt_log_dir=str(tmp_path / "ws" / "prompt_logs"),
        default_model="test/model",
        app_provider="",
        zai_api_key="",
        api_key="test-key",
    )


@pytest.fixture()
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture()
def client(
    settings: Settings, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    # The lifespan calls app.main.get_settings(); patch it to test settings so
    # the database/workspace land in tmp_path. Only the provider is overridden
    # afterwards — db/tools/workspace/settings come from the lifespan.
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    with TestClient(app) as c:
        c.app.state.provider = provider
        yield c


@pytest.fixture()
def db(client: TestClient, settings: Settings) -> Database:
    """Open the lifespan-created database file for direct seeding/inspection.

    Depends on ``client`` so the lifespan (which creates the schema) has run.
    """
    return Database(settings.db_path)
