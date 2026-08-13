"""Golden end-to-end run (step 08).

Orchestrates the full Catalog path on a real ``.docx`` through the service
layer — the same path a user drives in the UI:

1. ingest ``samples/golden.docx`` (kind=docx);
2. planner turn: the agent reads the document and produces a plan;
3. build a skill from the session (status=draft);
4. commit the skill;
5. ingest ``samples/golden2.docx`` and apply the committed skill to it.

Every acceptance criterion from
``docs/plan/night-shift/step-08-golden-polish.md`` is asserted inside
:func:`run_golden`, which takes its collaborators (provider/db/workspace) as
arguments so the orchestration is unit-testable with a scripted provider. The
``main`` entry point wires the real OpenRouter provider from the environment.

Requires a valid ``OPENROUTER_API_KEY`` and a tool-capable
``OPENROUTER_DEFAULT_MODEL``. Run from the ``backend/`` directory::

    python scripts/golden_run.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx

from app.agent.registry import ToolRegistry
from app.agent.runner import run_agent_collect
from app.api.skills import build_skill_from_session
from app.config import Settings
from app.documents.ingest import ingest_file
from app.documents.tools import build_document_tools
from app.llm.base import LLMProvider, Message
from app.llm.openrouter import OpenRouterProvider
from app.skills.apply import apply_skill_collect
from app.skills.repo_skill import get_skill, update_status
from app.storage.db import Database
from app.storage.repo_message import add_message
from app.storage.repo_session import create_session
from app.storage.repo_session_document import attach_documents

# Repo root = two parents up from backend/scripts/golden_run.py.
REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"

PLANNER_SYSTEM_PROMPT = (
    "Ты — планировщик Catalog. Изучи документ через read_document и составь "
    "задание для скилла: выделить ключевые тезисы документа и оформить их "
    "markdown-разметкой с обязательной секцией «Тезисы»."
)

PLAN_MESSAGE_TEMPLATE = (
    "Изучи документ {doc_id} через read_document и предложи скилл: выделить "
    "ключевые тезисы и оформить markdown с секцией «Тезисы». Для скилла задай "
    "проверки: non_empty, markdown_well_formed и has_section с heading «Тезисы»."
)

# Acceptance criteria constants (step-08 plan).
REQUIRED_CHECKS = {"non_empty", "markdown_well_formed", "has_section"}
ALLOWED_TOOL_SET = {"read_document", "list_documents"}


async def run_golden(
    *,
    provider: LLMProvider,
    db: Database,
    workspace_dir: str,
    samples_dir: Path,
    model: str,
) -> dict[str, Any]:
    """Run the full golden path; return a report dict.

    Raises :class:`AssertionError` on any unmet acceptance criterion, so a
    caller can treat a non-raising return as "green".
    """
    # 1. Ingest the first golden docx.
    golden1 = samples_dir / "golden.docx"
    if not golden1.exists():
        raise FileNotFoundError(f"sample not found: {golden1}")
    doc1 = ingest_file(
        db, workspace_dir, filename="golden.docx", content=golden1.read_bytes()
    )
    assert doc1.kind == "docx", f"expected kind=docx, got {doc1.kind}"

    # 2. Planner turn: read_document + plan, persisted to a session so the
    #    skill builder can read the conversation. The user message points the
    #    planner at the ingested document id so a live run actually reads it.
    plan_message = PLAN_MESSAGE_TEMPLATE.format(doc_id=doc1.id)
    session_id = create_session(db)
    attach_documents(db, session_id, [doc1.id])
    tools: ToolRegistry = build_document_tools(db, workspace_dir, session_id)
    add_message(db, session_id=session_id, role="user", content=plan_message)
    plan_text, _planner_trace, planner_capped = await run_agent_collect(
        provider=provider,
        model=model,
        system_prompt=PLANNER_SYSTEM_PROMPT,
        messages=[Message(role="user", content=plan_message)],
        tools=tools,
        use_stream=False,
    )
    if plan_text:
        add_message(
            db, session_id=session_id, role="assistant", content=plan_text
        )

    # 3. Build the skill from the session.
    settings = Settings(
        default_model=model, db_path=db.path, workspace_dir=workspace_dir
    )
    skill_id = await build_skill_from_session(
        provider=provider,
        db=db,
        base_tools=tools,
        settings=settings,
        session_id=session_id,
    )
    skill = get_skill(db, skill_id)
    assert skill is not None
    assert skill.status == "draft", f"expected status=draft, got {skill.status}"
    assert set(skill.config.allowed_tools) <= ALLOWED_TOOL_SET, (
        f"allowed_tools must be within {sorted(ALLOWED_TOOL_SET)}, "
        f"got {skill.config.allowed_tools}"
    )
    check_ids = {c.check for c in skill.config.verify_checks}
    assert REQUIRED_CHECKS <= check_ids, (
        f"verify_checks must include {sorted(REQUIRED_CHECKS)}, got {sorted(check_ids)}"
    )

    # 4. Commit the skill.
    update_status(db, skill_id, "committed")
    assert get_skill(db, skill_id).status == "committed"

    # 5. Ingest the second golden docx.
    golden2 = samples_dir / "golden2.docx"
    if not golden2.exists():
        raise FileNotFoundError(f"sample not found: {golden2}")
    doc2 = ingest_file(
        db, workspace_dir, filename="golden2.docx", content=golden2.read_bytes()
    )
    assert doc2.kind == "docx", f"expected kind=docx, got {doc2.kind}"
    attach_documents(db, session_id, [doc2.id])

    # 6. Apply the committed skill to the second document.
    result = await apply_skill_collect(
        provider=provider,
        db=db,
        workspace_dir=workspace_dir,
        skill=skill.config,
        skill_id=skill_id,
        input_doc_ids=[doc2.id],
        base_tools=tools,
        session_id=session_id,
    )
    assert result.status == "ok", f"apply status={result.status}"
    assert result.output_doc_id is not None, "apply produced no output_doc_id"
    assert "## Тезисы" in (result.result_text or ""), (
        "apply result missing '## Тезисы' section"
    )
    tool_calls = [e for e in result.trace.entries if e.kind == "tool_call"]
    assert any(e.data.get("name") == "read_document" for e in tool_calls), (
        "apply trace has no read_document tool_call"
    )

    return {
        "doc1_id": doc1.id,
        "doc2_id": doc2.id,
        "skill_id": skill_id,
        "skill_name": skill.config.name,
        "run_output_doc_id": result.output_doc_id,
        "result_preview": (result.result_text or "")[:200],
        "planner_capped": planner_capped,
        "apply_status": result.status,
    }


async def main() -> int:
    """Wire the real provider from the environment and run the golden path."""
    # Imported lazily so unit tests importing run_golden don't require env.
    from app.config import (
        OPENROUTER_API_KEY,
        OPENROUTER_BASE_URL,
        OPENROUTER_DEFAULT_MODEL,
    )

    if not OPENROUTER_API_KEY:
        print(
            "ERROR: OPENROUTER_API_KEY is not set. Add it to backend/.env",
            file=sys.stderr,
        )
        return 1
    if not OPENROUTER_DEFAULT_MODEL:
        print(
            "ERROR: OPENROUTER_DEFAULT_MODEL is not set (use a tool-capable model).",
            file=sys.stderr,
        )
        return 1

    with tempfile.TemporaryDirectory(prefix="catalog-golden-") as tmp:
        workspace = os.path.join(tmp, "workspace")
        catalog = os.path.join(workspace, ".catalog")
        os.makedirs(catalog, exist_ok=True)
        db_path = os.path.join(catalog, "index.db")
        db = Database(db_path)
        db.init_schema()
        client = httpx.AsyncClient(timeout=60.0)
        provider = OpenRouterProvider(
            client, OPENROUTER_API_KEY, OPENROUTER_BASE_URL
        )
        try:
            report = await run_golden(
                provider=provider,
                db=db,
                workspace_dir=workspace,
                samples_dir=SAMPLES_DIR,
                model=OPENROUTER_DEFAULT_MODEL,
            )
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
            print("\n=== GOLDEN RUN PASSED ===")
            return 0
        except AssertionError as exc:
            print(
                f"\n=== GOLDEN RUN FAILED — acceptance criterion not met: {exc} ===",
                file=sys.stderr,
            )
            return 2
        except Exception as exc:  # noqa: BLE001 — report any provider/agent error
            print(f"\n=== GOLDEN RUN ERROR: {exc!r} ===", file=sys.stderr)
            return 3
        finally:
            await client.aclose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
