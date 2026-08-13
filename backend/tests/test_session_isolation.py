from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from catalog.documents.ingest import ingest_file
from catalog.documents.tools import build_document_tools
from catalog.llm.base import CompletionResult, Message, ModelInfo, StreamDelta, ToolSpec
from catalog.skills.apply import apply_skill_collect
from catalog.skills.config import SkillConfig, VerifyCheck
from catalog.skills.repo_skill import create_skill
from catalog.storage.db import Database
from catalog.storage.repo_document import get_document, list_documents
from catalog.storage.repo_session import create_session
from catalog.storage.repo_session_document import (
    attach_documents,
    detach_documents,
    list_session_documents,
)


@pytest.fixture()
def db() -> Database:
    d = Database(":memory:")
    d.init_schema()
    return d


class _ScriptProvider:
    def __init__(self, script: list[CompletionResult]) -> None:
        self.script = list(script)

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
        return self.script.pop(0)

    async def stream_complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        tool_choice: str = "auto",
        reasoning: str = "",
    ):
        result = await self.complete(
            model, messages, tools, temperature, tool_choice, reasoning
        )
        if result.content:
            yield StreamDelta(text=result.content)
        yield StreamDelta(finish_reason=result.finish_reason or "stop")


async def _tool_list(reg) -> list:
    _, fn = reg.get("list_documents")
    return await fn()


async def _tool_read(reg, doc_id: str) -> dict:
    _, fn = reg.get("read_document")
    return await fn(doc_id=doc_id)


def test_tools_scoped_to_session(db: Database, tmp_path: Path) -> None:
    session_a = create_session(db)
    session_b = create_session(db)
    doc = ingest_file(db, tmp_path, filename="only-a.md", content=b"secret")
    attach_documents(db, session_a, [doc.id])

    tools_a = build_document_tools(db, tmp_path, session_a)
    tools_b = build_document_tools(db, tmp_path, session_b)

    listed_a = asyncio.run(_tool_list(tools_a))
    listed_b = asyncio.run(_tool_list(tools_b))
    assert [item["id"] for item in listed_a] == [doc.id]
    assert listed_b == []

    assert asyncio.run(_tool_read(tools_a, doc.id))["text"] == "secret"
    assert asyncio.run(_tool_read(tools_b, doc.id)) == {
        "error": "document_not_available_in_session"
    }


def test_detach_hides_document_from_tools(db: Database, tmp_path: Path) -> None:
    session_id = create_session(db)
    doc = ingest_file(db, tmp_path, filename="note.md", content=b"body")
    attach_documents(db, session_id, [doc.id])
    tools = build_document_tools(db, tmp_path, session_id)

    assert len(asyncio.run(_tool_list(tools))) == 1
    detach_documents(db, session_id, [doc.id])
    assert asyncio.run(_tool_list(tools)) == []
    assert get_document(db, doc.id) is not None


def test_apply_skill_persist_attaches_result_to_session(
    db: Database, tmp_path: Path
) -> None:
    session_id = create_session(db)
    skill = SkillConfig(
        name="summarizer",
        description="test",
        system_prompt="summarize",
        allowed_tools=["read_document"],
        model="test/model",
        temperature=0.0,
        max_iterations=4,
        max_retries=0,
        verify_checks=[VerifyCheck("non_empty")],
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc = ingest_file(db, tmp_path, filename="input.md", content=b"source")
    provider = _ScriptProvider(
        [
            CompletionResult(
                content="# Summary\n\nok",
                tool_calls=[],
                finish_reason="stop",
            )
        ]
    )

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(tmp_path),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc.id],
            base_tools=build_document_tools(db, tmp_path),
            session_id=session_id,
        )
    )

    assert result.status == "ok"
    assert result.output_doc_id is not None
    session_docs = list_session_documents(db, session_id)
    assert [d.id for d in session_docs] == [result.output_doc_id]
    assert get_document(db, result.output_doc_id) in list_documents(db)

    tools = build_document_tools(db, tmp_path, session_id)
    listed = asyncio.run(_tool_list(tools))
    assert [item["id"] for item in listed] == [result.output_doc_id]
    read = asyncio.run(_tool_read(tools, result.output_doc_id))
    assert "error" not in read
    assert "ok" in read["text"]


def test_session_reopen_restores_attached_docs(db: Database, tmp_path: Path) -> None:
    session_id = create_session(db)
    doc = ingest_file(db, tmp_path, filename="kept.md", content=b"kept body")
    attach_documents(db, session_id, [doc.id])

    restored = list_session_documents(db, session_id)
    assert [d.id for d in restored] == [doc.id]

    tools_after_reopen = build_document_tools(db, tmp_path, session_id)
    listed = asyncio.run(_tool_list(tools_after_reopen))
    assert [item["id"] for item in listed] == [doc.id]
    assert asyncio.run(_tool_read(tools_after_reopen, doc.id))["text"] == "kept body"


def test_global_list_unaffected_by_session_scope(
    db: Database, tmp_path: Path
) -> None:
    session_id = create_session(db)
    attached = ingest_file(db, tmp_path, filename="in-session.md", content=b"in")
    orphan = ingest_file(db, tmp_path, filename="global-only.md", content=b"out")
    attach_documents(db, session_id, [attached.id])

    global_ids = {d.id for d in list_documents(db)}
    assert global_ids == {attached.id, orphan.id}

    tools = build_document_tools(db, tmp_path, session_id)
    listed = asyncio.run(_tool_list(tools))
    assert [item["id"] for item in listed] == [attached.id]
    assert asyncio.run(_tool_read(tools, orphan.id)) == {
        "error": "document_not_available_in_session"
    }
