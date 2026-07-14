"""``apply_skill`` — full skill run with verify-retry and result persistence.

The apply loop (ADR-0001 + ADR-0006 + ADR-0007):

1. Load the input document (fail early if missing).
2. Filter the base tool registry down to ``skill.allowed_tools`` (fail-closed
   on unknown names — a skill must never silently drop a constraint).
3. For up to ``max_retries + 1`` attempts: run the agent loop, verify the
   output, emit a :class:`VerifyEvent`; on failure feed the reasons back and
   retry.
4. On success: persist the result as ``Document(kind=result_md)`` and write
   the file under ``workspace/results/``. On failure: keep the last text in
   the trace.
5. Record the outcome in ``skill_run`` and emit a :class:`FinishEvent`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from app.agent.events import AgentEvent, FinishEvent, VerifyEvent
from app.agent.registry import ToolRegistry
from app.agent.runner import run_agent_collect
from app.agent.trace import Trace
from app.llm.base import LLMProvider, Message
from app.skills.config import SkillConfig
from app.skills.repo_run import create_run, finish_run
from app.skills.verify import run_verify
from app.storage.db import Database
from app.storage.repo_document import create_document, get_document


@dataclass
class ApplyResult:
    """Return value of :func:`apply_skill_collect` (non-streaming wrapper)."""

    output_doc_id: str | None
    status: str  # "ok" | "failed"
    result_text: str | None
    trace: Trace


@dataclass
class _ApplyOutcome:
    """Mutable holder so the shared core can report status/doc_id to collectors."""

    output_doc_id: str | None = None
    status: str = "failed"
    result_text: str | None = None


async def _apply_core(
    *,
    provider: LLMProvider,
    db: Database,
    workspace_dir: str,
    skill: SkillConfig,
    skill_id: str,
    input_doc_id: str,
    base_tools: ToolRegistry,
    session_id: str | None,
    trace: Trace,
    outcome: _ApplyOutcome,
) -> AsyncIterator[AgentEvent]:
    """Shared apply loop: streams events, fills ``trace`` and ``outcome``.

    Both :func:`apply_skill` and :func:`apply_skill_collect` delegate here so
    the streaming and collect paths always agree (mirroring the
    ``_run_agent_core`` pattern in the agent runner).
    """
    # 1. Load input document.
    doc = get_document(db, input_doc_id)
    if doc is None:
        raise ValueError(f"input document not found: {input_doc_id}")

    # 2. Filter tools (fail-closed on unknown names).
    tools = base_tools.filter(skill.allowed_tools)

    # 3. Create the skill_run row.
    run_id = create_run(
        db, skill_id=skill_id, session_id=session_id, input_doc_id=input_doc_id
    )

    user_msg = Message(
        role="user",
        content=f"Обработай документ {input_doc_id} ({doc.title}).",
    )
    messages: list[Message] = [user_msg]

    last_text: str | None = None
    last_capped = False
    passed = False

    # max_retries = number of retries after the first attempt.
    for r in range(skill.max_retries + 1):
        text, run_trace, capped = await run_agent_collect(
            provider=provider,
            model=skill.model,
            system_prompt=skill.system_prompt,
            messages=messages,
            tools=tools,
            temperature=skill.temperature,
            max_iterations=skill.max_iterations,
            use_stream=False,
        )
        trace.entries.extend(run_trace.entries)
        last_text = text
        last_capped = capped

        result = run_verify(text or "", skill.verify_checks)
        yield VerifyEvent(iteration=r + 1, result=result)

        if result.passed:
            passed = True
            break

        # Feed verify failures back for the next attempt (if any left).
        if r < skill.max_retries:
            messages.append(Message(role="assistant", content=text or ""))
            messages.append(
                Message(
                    role="user",
                    content=(
                        "verify failed: "
                        + "; ".join(result.failures)
                        + ". Исправь и повтори."
                    ),
                )
            )

    # 5. Persist result on success.
    output_doc_id: str | None = None
    if passed:
        out_id = uuid.uuid4().hex
        create_document(
            db,
            title=f"{skill.name} — {doc.title}",
            path=f"results/{out_id}.md",
            kind="result_md",
            doc_id=out_id,
        )
        results_dir = Path(workspace_dir) / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        (results_dir / f"{out_id}.md").write_text(
            last_text or "", encoding="utf-8"
        )
        output_doc_id = out_id

    status = "ok" if passed else "failed"

    # 6. Record outcome.
    finish_run(
        db,
        run_id,
        status=status,
        output_doc_id=output_doc_id,
        trace=trace,
    )

    outcome.output_doc_id = output_doc_id
    outcome.status = status
    outcome.result_text = last_text

    # 7. Emit finish.
    yield FinishEvent(
        text=last_text,
        finish_reason="stop" if passed else ("capped" if last_capped else "verify_failed"),
        capped=(not passed) and last_capped,
        usage={},
    )


async def apply_skill(
    *,
    provider: LLMProvider,
    db: Database,
    workspace_dir: str,
    skill: SkillConfig,
    # Justified deviation from the plan signature: skill_run.skill_id is
    # NOT NULL, so the caller (step 06 build/apply planner) must supply the
    # id of the committed skill row. Carrying it on SkillConfig would couple
    # the frozen config to a specific DB row.
    skill_id: str,
    input_doc_id: str,
    base_tools: ToolRegistry,
    session_id: str | None = None,
) -> AsyncIterator[AgentEvent]:
    """Run a skill over a document, streaming :data:`AgentEvent` items.

    Emits the agent-loop events (step/tool/finish) interleaved with
    :class:`VerifyEvent` after each verify pass, plus a final
    :class:`FinishEvent`. Raises :class:`ValueError` for a missing input
    document or an unknown ``allowed_tools`` entry (fail-closed).
    """
    trace = Trace()
    outcome = _ApplyOutcome()
    async for event in _apply_core(
        provider=provider,
        db=db,
        workspace_dir=workspace_dir,
        skill=skill,
        skill_id=skill_id,
        input_doc_id=input_doc_id,
        base_tools=base_tools,
        session_id=session_id,
        trace=trace,
        outcome=outcome,
    ):
        yield event


async def apply_skill_collect(
    *,
    provider: LLMProvider,
    db: Database,
    workspace_dir: str,
    skill: SkillConfig,
    skill_id: str,
    input_doc_id: str,
    base_tools: ToolRegistry,
    session_id: str | None = None,
) -> ApplyResult:
    """Drain :func:`apply_skill` and return the final :class:`ApplyResult`."""
    trace = Trace()
    outcome = _ApplyOutcome()
    async for _event in _apply_core(
        provider=provider,
        db=db,
        workspace_dir=workspace_dir,
        skill=skill,
        skill_id=skill_id,
        input_doc_id=input_doc_id,
        base_tools=base_tools,
        session_id=session_id,
        trace=trace,
        outcome=outcome,
    ):
        pass
    return ApplyResult(
        output_doc_id=outcome.output_doc_id,
        status=outcome.status,
        result_text=outcome.result_text,
        trace=trace,
    )
