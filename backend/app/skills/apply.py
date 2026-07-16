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

import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from app.agent.events import AgentEvent, FinishEvent, VerifyEvent
from app.agent.logging import log_agent_event
from app.agent.registry import ToolRegistry
from app.agent.runner import _run_agent_core
from app.agent.trace import Trace, TraceEntry
from app.documents.extract import extract_text
from app.llm.base import LLMProvider, Message
from app.skills.config import SkillConfig
from app.skills.repo_run import create_run, finish_run
from app.skills.script_runner import ScriptRuntimeError, run_script_async
from app.skills.verify import run_verify
from app.storage.db import Database
from app.storage.repo_document import create_document, get_document

logger = logging.getLogger("app.skills.apply")


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
    run_id: str | None = None,
) -> AsyncIterator[AgentEvent]:
    """Shared apply loop: streams events, fills ``trace`` and ``outcome``.

    Both :func:`apply_skill` and :func:`apply_skill_collect` delegate here so
    the streaming and collect paths always agree (mirroring the
    ``_run_agent_core`` pattern in the agent runner).

    The retry loop iterates the agent core generator **directly** and forwards
    every inner event (Step/Token/ToolCall/ToolResult/Finish) to the stream,
    while accumulating the final text and ``trace`` entries — so a WS consumer
    sees the full agent activity, not just the verify/finish bookends.

    ``finish_run`` is guaranteed to run exactly once via ``try/except/finally``:
    a provider/agent exception marks the run ``failed`` (trace preserved) and
    re-raises, so an abandoned or errored stream never leaves an orphaned
    ``status='running'`` row.
    """
    # 1. Load input document.
    doc = get_document(db, input_doc_id)
    if doc is None:
        raise ValueError(f"input document not found: {input_doc_id}")

    # 2. Filter tools (fail-closed on unknown names).
    tools = base_tools.filter(skill.allowed_tools)

    # 3. Create the skill_run row (or reuse a pre-created one).
    if run_id is None:
        run_id = create_run(
            db, skill_id=skill_id, session_id=session_id, input_doc_id=input_doc_id
        )

    logger.info(
        "apply_skill start skill=%s skill_id=%s input_doc=%s run_id=%s",
        skill.name,
        skill_id,
        input_doc_id,
        run_id,
    )

    last_text: str | None = None
    last_capped = False
    passed = False
    output_doc_id: str | None = None
    # ``done`` guards finish_run so it runs exactly once across the normal
    # path, the exception path, and the finally safety net.
    done = False

    try:
        if skill.kind == "script":
            # ---- Deterministic script path (ADR-0014) ----
            # No agent loop, no LLM call at runtime: run the validated script
            # once over the document text. Retrying is pointless (same input
            # always yields the same output), so there is a single attempt and
            # a single verify pass — then the shared persist/finish tail.
            doc_text = extract_text(str(Path(workspace_dir) / doc.path), doc.kind)
            try:
                text = await run_script_async(skill.code, doc_text)
            except ScriptRuntimeError as exc:
                trace.entries.append(
                    TraceEntry(
                        kind="error",
                        iteration=1,
                        data={"script": True, "error": str(exc)},
                    )
                )
                raise
            trace.entries.append(
                TraceEntry(
                    kind="script",
                    iteration=1,
                    data={"ok": True, "chars": len(text)},
                )
            )
            last_text = text

            result = run_verify(text or "", skill.verify_checks)
            verify_event = VerifyEvent(iteration=1, result=result)
            yield verify_event
            log_agent_event(verify_event)
            passed = result.passed
        else:
            # ---- Agent path (ADR-0001/0002) ----
            user_msg = Message(
                role="user",
                content=f"Обработай документ {input_doc_id} ({doc.title}).",
            )
            messages: list[Message] = [user_msg]

            # max_retries = number of retries after the first attempt.
            for r in range(skill.max_retries + 1):
                text: str | None = None
                capped = False
                # Drive the agent loop directly: forward each inner event to the
                # stream and capture the final text/capped from its FinishEvent,
                # while _run_agent_core appends to our shared ``trace``.
                async for event in _run_agent_core(
                    provider=provider,
                    model=skill.model,
                    system_prompt=skill.system_prompt,
                    messages=messages,
                    tools=tools,
                    temperature=skill.temperature,
                    max_iterations=skill.max_iterations,
                    use_stream=False,
                    trace=trace,
                ):
                    yield event
                    # Inner agent events are already logged by _run_agent_core
                    # (single source of truth); re-logging here would duplicate them.
                    if isinstance(event, FinishEvent):
                        text = event.text
                        capped = event.capped

                last_text = text
                last_capped = capped

                result = run_verify(text or "", skill.verify_checks)
                verify_event = VerifyEvent(iteration=r + 1, result=result)
                yield verify_event
                log_agent_event(verify_event)

                if result.passed:
                    passed = True
                    break

                # Feed verify failures back for the next attempt (if any left).
                if r < skill.max_retries:
                    logger.info(
                        "verify failed, retry %d/%d failures=%s",
                        r + 1,
                        skill.max_retries,
                        list(result.failures),
                    )
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
            logger.info("apply_skill persisted output_doc_id=%s", out_id)

        status = "ok" if passed else "failed"

        # 6. Record outcome (normal path).
        finish_run(
            db,
            run_id,
            status=status,
            output_doc_id=output_doc_id,
            trace=trace,
        )
        done = True

        outcome.output_doc_id = output_doc_id
        outcome.status = status
        outcome.result_text = last_text

        logger.info(
            "apply_skill done status=%s output_doc_id=%s", status, output_doc_id
        )

        # 7. Emit finish.
        finish_apply = FinishEvent(
            text=last_text,
            finish_reason="stop" if passed else ("capped" if last_capped else "verify_failed"),
            capped=(not passed) and last_capped,
            usage={},
        )
        yield finish_apply
        # apply-finish is not re-logged here: the agent FinishEvent was already
        # logged once by _run_agent_core, and "apply_skill done" is the
        # authoritative completion line for the apply layer.
    except Exception:
        # Provider/agent failure: persist a failed run (trace preserved) so the
        # row is never left 'running', then re-raise — the stream consumer gets
        # the error rather than a silently truncated event sequence.
        logger.error("apply_skill failed", exc_info=True)
        if not done:
            finish_run(
                db,
                run_id,
                status="failed",
                output_doc_id=None,
                trace=trace,
            )
            done = True
        raise
    finally:
        # Safety net for early stream termination (consumer break/abandon):
        # ensure finish_run ran at least once. ``done`` prevents double-calls.
        if not done:
            finish_run(
                db,
                run_id,
                status="failed",
                output_doc_id=None,
                trace=trace,
            )
            done = True


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
    run_id: str | None = None,
) -> AsyncIterator[AgentEvent]:
    """Run a skill over a document, streaming :data:`AgentEvent` items.

    Emits the agent-loop events (step/tool/finish) interleaved with
    :class:`VerifyEvent` after each verify pass, plus a final
    :class:`FinishEvent`. Raises :class:`ValueError` for a missing input
    document or an unknown ``allowed_tools`` entry (fail-closed).

    When ``run_id`` is supplied the existing ``skill_run`` row is reused
    (used by the ``WS /runs/{id}/stream`` endpoint which creates the row in
    ``POST /skills/{id}/apply``); otherwise a new row is created.
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
        run_id=run_id,
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
    run_id: str | None = None,
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
        run_id=run_id,
    ):
        pass
    return ApplyResult(
        output_doc_id=outcome.output_doc_id,
        status=outcome.status,
        result_text=outcome.result_text,
        trace=trace,
    )
