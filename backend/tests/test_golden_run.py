from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import docx

from app.llm.base import (
    CompletionResult,
    LLMProvider,
    Message,
    ModelInfo,
    StreamDelta,
    ToolCall,
    ToolSpec,
)
from app.storage.db import Database
from scripts.golden_run import run_golden


class _GoldenProvider:
    """Scripted provider driving the golden path in a fixed call order.

    The order is fixed by :func:`run_golden`:

    1. planner turn     -> plain plan text (no tool call);
    2. build_skill turn -> ``build_skill`` tool call carrying a valid config;
    3. apply turn #1    -> ``read_document`` tool call (the ``doc_id`` is pulled
       from the apply user message so the real document is actually read);
    4. apply turn #2    -> final markdown containing the ``## Тезисы`` section,
       which satisfies every verify check of the built skill.

    No network/keys are involved — this is a deterministic, in-process run.
    """

    def __init__(self) -> None:
        self.calls = 0

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
        self.calls += 1
        if self.calls == 1:
            return CompletionResult(
                content="План: выделить тезисы и оформить markdown с секцией «Тезисы».",
                tool_calls=[],
                finish_reason="stop",
            )
        if self.calls == 2:
            return CompletionResult(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="build_skill_1",
                        name="build_skill",
                        arguments={
                            "name": "tezisy",
                            "description": "Выделить ключевые тезисы документа в markdown.",
                            "system_prompt": "Ты выделяешь ключевые тезисы документа.",
                            "allowed_tools": ["read_document", "list_documents"],
                            "model": model,
                            "temperature": 0.0,
                            "max_iterations": 6,
                            "max_retries": 2,
                            "verify_checks": [
                                {"check": "non_empty"},
                                {"check": "markdown_well_formed"},
                                {"check": "has_section", "params": {"heading": "Тезисы"}},
                            ],
                            "output_kind": "md",
                        },
                    )
                ],
                finish_reason="tool_calls",
            )
        if self.calls == 3:
            return CompletionResult(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="read_doc_1",
                        name="read_document",
                        arguments={"doc_id": _extract_doc_id(messages)},
                    )
                ],
                finish_reason="tool_calls",
            )
        # call 4: final markdown result satisfying all verify checks.
        return CompletionResult(
            content=(
                "## Тезисы\n\n"
                "- Первый ключевой тезис документа.\n"
                "- Второй ключевой тезис документа."
            ),
            tool_calls=[],
            finish_reason="stop",
        )

    async def stream_complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        reasoning: str = "",
    ) -> Any:
        yield StreamDelta(content="")


# Static protocol check: _GoldenProvider satisfies LLMProvider.
_PROVIDER: LLMProvider = _GoldenProvider()  # type: ignore[assignment]


_APPLY_DOC_ID_RE = re.compile(r"Обработай документ (\S+)")


def _extract_doc_id(messages: list[Message]) -> str:
    """Pull the input document id out of the apply user message."""
    for m in messages:
        if m.role == "user" and m.content:
            match = _APPLY_DOC_ID_RE.search(m.content)
            if match:
                return match.group(1)
    raise AssertionError("no doc_id found in apply user message")


def _make_docx(path: Path, paragraphs: list[str]) -> None:
    """Generate a minimal valid .docx readable by python-docx (kind=docx)."""
    document = docx.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(str(path))


def test_golden_run_end_to_end(tmp_path: Path) -> None:
    """Full golden path through the service layer with a scripted provider.

    Ingest -> plan -> build skill -> commit -> apply on a second document, with
    every acceptance criterion from step-08 asserted inside ``run_golden``
    (a non-raising return means green).
    """
    samples_dir = tmp_path / "samples"
    samples_dir.mkdir()
    _make_docx(
        samples_dir / "golden.docx",
        ["Отчёт за квартал", "Первый ключевой тезис.", "Второй ключевой тезис."],
    )
    _make_docx(
        samples_dir / "golden2.docx",
        ["Другой отчёт", "Содержит иные тезисы для применения скилла."],
    )

    workspace = tmp_path / "ws"
    catalog = workspace / ".catalog"
    catalog.mkdir(parents=True)
    db = Database(str(catalog / "index.db"))
    db.init_schema()
    workspace = str(workspace)

    report = asyncio.run(
        run_golden(
            provider=_GoldenProvider(),
            db=db,
            workspace_dir=workspace,
            samples_dir=samples_dir,
            model="test/model",
        )
    )

    assert report["apply_status"] == "ok"
    assert report["run_output_doc_id"]
    assert "## Тезисы" in report["result_preview"]
