"""``apply_skill`` — full skill run with verify-retry and result persistence.

The apply loop (ADR-0001 + ADR-0006 + ADR-0007):

1. Load the input document (fail early if missing).
2. Filter the base tool registry down to ``skill.allowed_tools`` (fail-closed
   on unknown names — a skill must never silently drop a constraint).
3. For up to ``max_retries + 1`` attempts: run the agent loop, verify the
   output, emit a :class:`VerifyEvent`; on failure feed the reasons back and
   retry.
4. On success: when ``persist=True`` (CATALOG-18; the default, matching the
   pre-CATALOG-18 behaviour), persist the result as ``Document(kind=result_md)``
   and write the file under ``workspace/results/``. When ``persist=False``
   the result stays on screen only — no document is created, but the raw text
   is still stored on the run row (``result_text``) so it can be materialized
   later via ``POST /runs/{id}/save``. On failure: keep the last text in the
   trace.
5. Record the outcome in ``skill_run`` and emit a :class:`FinishEvent`.
"""

from __future__ import annotations

import logging
import time
import uuid
from asyncio import CancelledError
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from pathlib import Path

from catalog.agent.events import AgentEvent, FinishEvent, RunMetaEvent, ScriptEvent, VerifyEvent
from catalog.agent.logging import log_agent_event
from catalog.agent.registry import ToolRegistry
from catalog.agent.runner import _run_agent_core
from catalog.agent.trace import Trace, TraceEntry
from catalog.documents.extract import extract_text
from catalog.documents.ingest import (
    allocate_rel_path,
    content_hash_bytes,
    safe_filename,
)
from catalog.documents.obsidian import (
    build_title_to_stem_map,
    ensure_parent_wikilinks,
    rewrite_wiki_links,
)
from catalog.llm.base import LLMProvider, Message
from catalog.skills.config import PipelineStep, SkillConfig, ensure_read_document_tool
from catalog.skills.repo_run import claim_run, create_run, finish_run, get_run
from catalog.skills.script_runner import ScriptRuntimeError, run_script_async
from catalog.skills.verify import run_verify
from catalog.storage.db import Database
from catalog.storage.repo_document import create_document, get_document
from catalog.storage.repo_session_document import attach_documents

logger = logging.getLogger("catalog.skills.apply")

PipelineValue = str | list[str]


def _value_as_text(value: PipelineValue) -> str:
    if isinstance(value, list):
        if len(value) == 1:
            return value[0]
        return "\n\n---\n\n".join(value)
    return value


def _value_as_documents(value: PipelineValue) -> list[str]:
    if isinstance(value, list):
        return list(value)
    return [value]


def _with_step_id(event: AgentEvent, step_id: str) -> AgentEvent:
    if hasattr(event, "step_id"):
        return replace(event, step_id=step_id)
    return event


def _pipeline_step_input(
    step: PipelineStep,
    current: PipelineValue | None,
    doc_texts: list[str],
) -> PipelineValue:
    if step.input == "documents" or current is None:
        return doc_texts[0] if len(doc_texts) == 1 else list(doc_texts)
    return current


def _pipeline_llm_user_content(
    *,
    step_input: PipelineValue,
    from_documents: bool,
    docs: list,
    input_doc_ids: list[str],
    doc_texts: list[str],
) -> str:
    if from_documents:
        link_hint = (
            "Не вставляй связи с входными документами в текст ответа — "
            "система добавит раздел «Ссылки» при сохранении. "
            "Если нужны другие Obsidian-ссылки [[...]], используй имя файла "
            "(stem без расширения и пути), а не title."
        )
        content_note = (
            "Ниже приведён полный текст каждого входного документа — "
            "опирайся на него. Это не вложение файла: текст уже в этом "
            "сообщении. При необходимости дополнительно вызови "
            "read_document(doc_id=...)."
        )
        stem_lines = "\n".join(
            f"- «{d.title}» → [[{Path(d.path).stem}]]" for d in docs
        )
        inline_blocks = "\n\n".join(
            f"--- документ {did}: {d.title} ---\n{text}"
            for did, d, text in zip(input_doc_ids, docs, doc_texts)
        )
        if len(docs) == 1:
            return (
                f"Обработай документ {input_doc_ids[0]} ({docs[0].title}).\n"
                f"{content_note}\n{link_hint}\n{stem_lines}\n\n{inline_blocks}"
            )
        listing = ", ".join(
            f"{did} ({d.title})" for did, d in zip(input_doc_ids, docs)
        )
        return (
            f"Обработай документы: {listing}.\n"
            f"{content_note}\n{link_hint}\n{stem_lines}\n\n{inline_blocks}"
        )
    if isinstance(step_input, list):
        blocks = "\n\n".join(
            f"--- фрагмент {i + 1} ---\n{text}"
            for i, text in enumerate(step_input)
        )
        return f"Обработай следующие фрагменты.\n\n{blocks}"
    return f"Обработай следующий текст.\n\n{step_input}"


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
    input_doc_ids: list[str],
    base_tools: ToolRegistry,
    session_id: str | None,
    trace: Trace,
    outcome: _ApplyOutcome,
    run_id: str | None = None,
    provider_name: str = "",
    persist: bool = True,
    user_prompt: str | None = None,
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

    CATALOG-4: ``input_doc_ids`` carries one or more input documents. They are
    all loaded here (any missing → ``ValueError``); a skill declaring
    ``input_arity`` rejects a count mismatch (→ ``ValueError``); the agent start
    message lists every input.

    CATALOG-56: ``user_prompt`` is an optional runtime clarification appended
    to the agent start user message; script skills ignore it.
    """
    # 1. Load ALL input documents (fail early if any is missing).
    if not input_doc_ids:
        raise ValueError("apply requires at least one input document")
    docs = []
    for doc_id in input_doc_ids:
        d = get_document(db, doc_id)
        if d is None:
            raise ValueError(f"input document not found: {doc_id}")
        docs.append(d)

    # Arity check (CATALOG-4): a skill may declare how many inputs it expects.
    if skill.input_arity is not None and len(input_doc_ids) != skill.input_arity:
        raise ValueError(
            f"skill expects {skill.input_arity} input document(s), "
            f"got {len(input_doc_ids)}"
        )

    runtime_prompt = (user_prompt or "").strip() or None

    if skill.kind == "agent":
        tools = base_tools.filter(ensure_read_document_tool(skill.allowed_tools))
    else:
        tools = base_tools.filter(skill.allowed_tools)

    doc_texts = [
        extract_text(str(Path(workspace_dir) / d.path), d.kind) for d in docs
    ]

    # 3. Create the skill_run row (or reuse a pre-created one).
    if run_id is None:
        run_id = create_run(
            db,
            skill_id=skill_id,
            session_id=session_id,
            input_doc_ids=input_doc_ids,
            persist=persist,
            user_prompt=runtime_prompt,
        )
        if not claim_run(db, run_id):
            raise RuntimeError(f"failed to claim run {run_id}")
    else:
        existing_run = get_run(db, run_id)
        if existing_run is not None:
            if session_id is None:
                session_id = existing_run["session_id"]
            if runtime_prompt is None:
                runtime_prompt = (
                    (existing_run.get("user_prompt") or "").strip() or None
                )

    logger.info(
        "apply_skill start skill=%s skill_id=%s input_docs=%d run_id=%s",
        skill.name,
        skill_id,
        len(input_doc_ids),
        run_id,
    )

    last_text: str | None = None
    last_capped = False
    passed = False
    output_doc_id: str | None = None
    # ``done`` guards finish_run so it runs exactly once across the normal
    # path, the exception path, and the finally safety net.
    done = False

    # CATALOG-16: run-level meta is the first event on the wire so the trace
    # feed can render model/provider/kind/prompt up front instead of only the
    # iteration bookends.
    meta_event = RunMetaEvent(
        model=skill.model,
        provider=provider_name,
        skill_kind=skill.kind,
        system_prompt=skill.system_prompt,
        input_docs=list(input_doc_ids),
    )
    yield meta_event
    log_agent_event(meta_event)

    try:
        if skill.kind == "script":
            # ---- Deterministic script path (ADR-0014) ----
            # No agent loop, no LLM call at runtime: run the validated script
            # once over the document text. Retrying is pointless (same input
            # always yields the same output), so there is a single attempt and
            # a single verify pass — then the shared persist/finish tail.
            # Single document → its text verbatim. Multiple → joined with a
            # separator so the script sees all input content.
            doc_text = doc_texts[0] if len(doc_texts) == 1 else "\n\n---\n\n".join(doc_texts)
            # CATALOG-3/16: surface script execution as granular trace steps
            # (start/done/error with a code snippet, the return value and the
            # wall-clock duration) so a script run is not an opaque black box.
            script_start = ScriptEvent(stage="start", snippet=skill.code)
            yield script_start
            log_agent_event(script_start)
            t0 = time.perf_counter()
            try:
                text = await run_script_async(
                    skill.code, doc_text, documents=doc_texts
                )
                if isinstance(text, list):
                    text = _value_as_text(text)
            except ScriptRuntimeError as exc:
                script_error = ScriptEvent(
                    stage="error", error=str(exc), duration=time.perf_counter() - t0
                )
                yield script_error
                log_agent_event(script_error)
                trace.entries.append(
                    TraceEntry(
                        kind="error",
                        iteration=1,
                        data={"script": True, "error": str(exc)},
                    )
                )
                raise
            script_done = ScriptEvent(
                stage="done", return_value=text, duration=time.perf_counter() - t0
            )
            yield script_done
            log_agent_event(script_done)
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
        elif skill.kind == "pipeline":
            current: PipelineValue | None = None
            for index, step in enumerate(skill.steps):
                step_input = _pipeline_step_input(step, current, doc_texts)
                from_documents = step.input == "documents" or current is None
                if step.type == "script":
                    doc_text = _value_as_text(step_input)
                    docs_list = _value_as_documents(step_input)
                    script_start = ScriptEvent(
                        stage="start", snippet=step.code, step_id=step.id
                    )
                    yield script_start
                    log_agent_event(script_start)
                    t0 = time.perf_counter()
                    try:
                        text = await run_script_async(
                            step.code, doc_text, documents=docs_list
                        )
                    except ScriptRuntimeError as exc:
                        script_error = ScriptEvent(
                            stage="error",
                            error=str(exc),
                            duration=time.perf_counter() - t0,
                            step_id=step.id,
                        )
                        yield script_error
                        log_agent_event(script_error)
                        trace.entries.append(
                            TraceEntry(
                                kind="error",
                                iteration=index + 1,
                                data={
                                    "script": True,
                                    "error": str(exc),
                                    "step_id": step.id,
                                },
                            )
                        )
                        raise
                    display = _value_as_text(text)
                    script_done = ScriptEvent(
                        stage="done",
                        return_value=display,
                        duration=time.perf_counter() - t0,
                        step_id=step.id,
                    )
                    yield script_done
                    log_agent_event(script_done)
                    trace.entries.append(
                        TraceEntry(
                            kind="script",
                            iteration=index + 1,
                            data={
                                "ok": True,
                                "chars": len(display),
                                "step_id": step.id,
                            },
                        )
                    )
                    current = text
                    last_text = display
                elif step.type == "llm":
                    step_tools = base_tools.filter(
                        ensure_read_document_tool(step.allowed_tools)
                    )
                    start_content = _pipeline_llm_user_content(
                        step_input=step_input,
                        from_documents=from_documents,
                        docs=docs,
                        input_doc_ids=input_doc_ids,
                        doc_texts=doc_texts,
                    )
                    messages: list[Message] = [
                        Message(role="user", content=start_content)
                    ]
                    text = None
                    capped = False
                    before = len(trace.entries)
                    async for event in _run_agent_core(
                        provider=provider,
                        model=step.model or skill.model,
                        system_prompt=step.system_prompt,
                        messages=messages,
                        tools=step_tools,
                        temperature=skill.temperature,
                        max_iterations=skill.max_iterations,
                        use_stream=False,
                        trace=trace,
                        reasoning=step.reasoning or skill.reasoning,
                    ):
                        tagged = _with_step_id(event, step.id)
                        yield tagged
                        if isinstance(event, FinishEvent):
                            text = event.text
                            capped = event.capped
                    for entry in trace.entries[before:]:
                        entry.data["step_id"] = step.id
                    current = text or ""
                    last_text = current
                    last_capped = capped
                else:
                    raise ValueError(
                        f"unknown pipeline step type: {step.type!r}"
                    )
            final_text = last_text or ""
            result = run_verify(final_text, skill.verify_checks)
            verify_event = VerifyEvent(iteration=1, result=result)
            yield verify_event
            log_agent_event(verify_event)
            passed = result.passed
        else:
            # ---- Agent path (ADR-0001/0002) ----
            # Build the start message listing every input document (CATALOG-4).
            link_hint = (
                "Не вставляй связи с входными документами в текст ответа — "
                "система добавит раздел «Ссылки» при сохранении. "
                "Если нужны другие Obsidian-ссылки [[...]], используй имя файла "
                "(stem без расширения и пути), а не title."
            )
            content_note = (
                "Ниже приведён полный текст каждого входного документа — "
                "опирайся на него. Это не вложение файла: текст уже в этом "
                "сообщении. При необходимости дополнительно вызови "
                "read_document(doc_id=...)."
            )
            stem_lines = "\n".join(
                f"- «{d.title}» → [[{Path(d.path).stem}]]" for d in docs
            )
            inline_blocks = "\n\n".join(
                f"--- документ {did}: {d.title} ---\n{text}"
                for did, d, text in zip(input_doc_ids, docs, doc_texts)
            )
            if len(docs) == 1:
                start_content = (
                    f"Обработай документ {input_doc_ids[0]} ({docs[0].title}).\n"
                    f"{content_note}\n{link_hint}\n{stem_lines}\n\n{inline_blocks}"
                )
            else:
                listing = ", ".join(
                    f"{did} ({d.title})" for did, d in zip(input_doc_ids, docs)
                )
                start_content = (
                    f"Обработай документы: {listing}.\n"
                    f"{content_note}\n{link_hint}\n{stem_lines}\n\n{inline_blocks}"
                )
            if runtime_prompt is not None:
                start_content = (
                    f"{start_content}\n\nУточнение к заданию:\n{runtime_prompt}"
                )
            user_msg = Message(role="user", content=start_content)
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
                    reasoning=skill.reasoning,
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

        # 5. Persist result on success (CATALOG-18: only in "persist" mode —
        # "preview" mode leaves the result on screen, materialized later via
        # POST /runs/{id}/save if the user chooses to).
        if passed and persist:
            if len(docs) == 1:
                result_title = f"{skill.name} — {docs[0].title}"
            else:
                result_title = f"{skill.name} — {docs[0].title} (+{len(docs) - 1})"
            out_id = uuid.uuid4().hex
            workspace_path = Path(workspace_dir)
            rel_path = allocate_rel_path(
                workspace_path,
                safe_filename(result_title, ".md"),
                subdir="results",
            )
            last_text = rewrite_wiki_links(
                last_text or "", build_title_to_stem_map(db)
            )
            last_text = ensure_parent_wikilinks(
                last_text,
                [Path(d.path).stem for d in docs],
            )
            dest = workspace_path / rel_path
            dest.write_text(last_text, encoding="utf-8")
            st = dest.stat()
            create_document(
                db,
                title=result_title,
                path=rel_path,
                kind="result_md",
                doc_id=out_id,
                mtime=st.st_mtime,
                size=st.st_size,
                content_hash=content_hash_bytes(
                    last_text.encode("utf-8")
                ),
            )
            output_doc_id = out_id
            if session_id is not None:
                attach_documents(db, session_id, [out_id])
            logger.info("apply_skill persisted output_doc_id=%s", out_id)

        status = "ok" if passed else "failed"

        # 6. Record outcome (normal path). ``result_text`` is stored
        # regardless of ``persist`` so a preview run can still be saved later.
        finish_run(
            db,
            run_id,
            status=status,
            output_doc_id=output_doc_id,
            trace=trace,
            result_text=last_text,
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
    except CancelledError:
        # CATALOG-11: the apply task was cancelled (user pressed "Stop" in the
        # UI). Distinguish this from a provider/agent failure: the run is marked
        # ``cancelled`` (not ``failed``) so the trace feed and the run row
        # reflect the user's intent. The partial trace is preserved. The
        # CancelledError is re-raised so the WS handler can send its
        # authoritative ``finish{status:"cancelled"}`` frame and the standard
        # asyncio cancellation propagates through the whole stack.
        logger.info("apply_skill cancelled run_id=%s", run_id)
        if not done:
            finish_run(
                db,
                run_id,
                status="cancelled",
                output_doc_id=None,
                trace=trace,
                result_text=last_text,
            )
            done = True
        outcome.status = "cancelled"
        raise
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
                result_text=last_text,
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
                result_text=last_text,
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
    input_doc_ids: list[str],
    base_tools: ToolRegistry,
    session_id: str | None = None,
    run_id: str | None = None,
    provider_name: str = "",
    persist: bool = True,
    user_prompt: str | None = None,
) -> AsyncIterator[AgentEvent]:
    """Run a skill over one or more documents, streaming :data:`AgentEvent` items.

    Emits the agent-loop events (step/tool/finish) interleaved with
    :class:`VerifyEvent` after each verify pass, plus a final
    :class:`FinishEvent`. Raises :class:`ValueError` for a missing input
    document, an arity mismatch, or an unknown ``allowed_tools`` entry
    (fail-closed).

    When ``run_id`` is supplied the existing ``skill_run`` row is reused
    (used by the ``WS /runs/{id}/stream`` endpoint which creates the row in
    ``POST /skills/{id}/apply``); otherwise a new row is created.

    ``provider_name`` (CATALOG-16) is the resolved provider name surfaced via
    the opening :class:`RunMetaEvent`; empty when unknown.

    ``persist`` (CATALOG-18) selects the output mode: ``True`` (default)
    auto-creates a ``result_md`` document on success; ``False`` leaves the
    result on screen only (``result_text`` is still recorded on the run row).

    ``user_prompt`` (CATALOG-56) is an optional runtime clarification for
    agent skills; ignored for ``kind == "script"``.
    """
    trace = Trace()
    outcome = _ApplyOutcome()
    async for event in _apply_core(
        provider=provider,
        db=db,
        workspace_dir=workspace_dir,
        skill=skill,
        skill_id=skill_id,
        input_doc_ids=input_doc_ids,
        base_tools=base_tools,
        session_id=session_id,
        trace=trace,
        outcome=outcome,
        run_id=run_id,
        provider_name=provider_name,
        persist=persist,
        user_prompt=user_prompt,
    ):
        yield event


async def apply_skill_collect(
    *,
    provider: LLMProvider,
    db: Database,
    workspace_dir: str,
    skill: SkillConfig,
    skill_id: str,
    input_doc_ids: list[str],
    base_tools: ToolRegistry,
    session_id: str | None = None,
    run_id: str | None = None,
    provider_name: str = "",
    persist: bool = True,
    user_prompt: str | None = None,
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
        input_doc_ids=input_doc_ids,
        base_tools=base_tools,
        session_id=session_id,
        trace=trace,
        outcome=outcome,
        run_id=run_id,
        provider_name=provider_name,
        persist=persist,
        user_prompt=user_prompt,
    ):
        pass
    return ApplyResult(
        output_doc_id=outcome.output_doc_id,
        status=outcome.status,
        result_text=outcome.result_text,
        trace=trace,
    )
