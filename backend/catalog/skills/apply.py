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

import hashlib
import logging
import re
import time
import uuid
from asyncio import CancelledError
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from pathlib import Path

from catalog.agent.events import (
    AgentEvent,
    FinishEvent,
    RunMetaEvent,
    ScriptEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    VerifyEvent,
)
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
from catalog.llm.factory import provider_for_skill
from catalog.documents.tools import build_document_tools
from catalog.skills.budget import (
    SkillBudget,
    SkillCallContext,
    current_skill_budget,
    estimate_skill_budget,
    nested_deadline_exceeded,
    nested_skill_hold,
    skill_hold_active,
)
from catalog.skills.config import (
    MAX_COLLECTION_DOCUMENTS,
    MAX_SKILL_OUTPUTS,
    PipelineStep,
    SkillConfig,
    SkillOutput,
    ensure_read_document_tool,
)
from catalog.skills.emit_output import (
    named_output_failures,
    named_outputs_prompt,
    primary_output_text,
    register_emit_output,
    uses_emit_output,
)
from catalog.skills.repo_run import claim_run, create_run, finish_run, get_run
from catalog.skills.script_runner import ScriptRuntimeError, run_skill_script_async
from catalog.skills.verify import VerifyResult, run_verify_async
from catalog.storage.db import Database
from catalog.storage.repo_document import create_document, get_document
from catalog.storage.repo_session_document import attach_documents

logger = logging.getLogger("catalog.skills.apply")

PipelineValue = str | list[str]
# ADR-0025: the value of a single named output. A ``multiple`` key's value is
# ``list[str]`` (one element per document to persist); a regular key's value
# is ``str``. Structurally identical to ``PipelineValue`` but named separately
# because the two live at different semantic layers (a pipeline step's whole
# value vs. one entry of an ``artifacts`` dict).
ArtifactValue = str | list[str]


class PipelineStepError(RuntimeError):
    pass


class NamedOutputsError(RuntimeError):
    pass


class CollectionLimitError(RuntimeError):
    """Raised when a run would persist more collection documents than
    ``MAX_COLLECTION_DOCUMENTS`` allows (ADR-0025). Always raised *before* any
    file is written, so a run failing this check leaves no partial output."""


def _value_as_text(value: PipelineValue) -> str:
    if isinstance(value, dict):
        raise TypeError("named outputs dict is not a pipeline value")
    if isinstance(value, list):
        if len(value) == 1:
            return value[0]
        return "\n\n---\n\n".join(value)
    return value


def _value_as_documents(value: PipelineValue) -> list[str]:
    if isinstance(value, dict):
        raise TypeError("named outputs dict is not a pipeline value")
    if isinstance(value, list):
        return list(value)
    return [value]


def _match_named_outputs(
    skill: SkillConfig, value: dict[str, ArtifactValue]
) -> dict[str, ArtifactValue]:
    """Validate a script/agent result dict against ``skill.outputs`` (ADR-0025).

    Beyond the pre-existing ``unknown``/``missing``/``empty`` checks, each
    present key's *value type* is now checked against its declaration:
    ``multiple`` requires a non-empty ``list[str]`` with no blank elements;
    a regular key requires a non-empty ``str``. A type mismatch is reported
    separately from ``empty`` so ``[]`` and "string instead of a list" surface
    distinct, actionable reasons in the trace.
    """
    declared_items = {item.key: item for item in skill.outputs}
    declared = list(declared_items)
    if not declared:
        raise NamedOutputsError(
            "skill returned a dict but SkillConfig.outputs is empty"
        )
    if len(value) > MAX_SKILL_OUTPUTS:
        raise NamedOutputsError(
            f"too many output keys: {len(value)} (max {MAX_SKILL_OUTPUTS})"
        )
    extra = sorted(set(value) - set(declared))
    missing = [key for key in declared if key not in value]
    expected_list: list[str] = []
    expected_text: list[str] = []
    empty: list[str] = []
    empty_element: list[str] = []
    for key in declared:
        if key not in value:
            continue
        item = declared_items[key]
        raw_value = value[key]
        if item.multiple:
            if not isinstance(raw_value, list):
                expected_list.append(key)
            elif not raw_value:
                empty.append(key)
            elif any(not (elem or "").strip() for elem in raw_value):
                empty_element.append(key)
        else:
            if isinstance(raw_value, list):
                expected_text.append(key)
            elif not (raw_value or "").strip():
                empty.append(key)
    parts: list[str] = []
    if extra:
        parts.append("unknown output key(s): " + ", ".join(extra))
    if missing:
        parts.append("missing output key(s): " + ", ".join(missing))
    if expected_list:
        parts.append("expected list for output key(s): " + ", ".join(expected_list))
    if expected_text:
        parts.append("expected text for output key(s): " + ", ".join(expected_text))
    if empty:
        parts.append("empty output value(s): " + ", ".join(empty))
    if empty_element:
        parts.append("empty output element(s): " + ", ".join(empty_element))
    if parts:
        raise NamedOutputsError("; ".join(parts))
    return {key: value[key] for key in declared}


def _finalize_script_result(
    skill: SkillConfig, raw: str | list[str] | dict[str, ArtifactValue]
) -> tuple[str, dict[str, ArtifactValue]]:
    if isinstance(raw, dict):
        artifacts = _match_named_outputs(skill, raw)
        # ADR-0025 (Decision 3): a collection primary (outputs[0].multiple)
        # has two representations of the same value — the joined text here
        # (verify / pipeline value / skill-as-tool) and the N-document split
        # in persist_run_outputs, which reads ``artifacts`` unmodified.
        return _value_as_text(artifacts[skill.outputs[0].key]), artifacts
    if skill.outputs:
        raise NamedOutputsError(
            "skill declared outputs but script did not return a dict"
        )
    if isinstance(raw, list):
        return _value_as_text(raw), {}
    return raw, {}


def _record_outputs_error(
    trace: Trace, iteration: int, error: str, step_id: str | None = None
) -> None:
    data: dict[str, object] = {"outputs": True, "error": error}
    if step_id is not None:
        data["step_id"] = step_id
    trace.entries.append(TraceEntry(kind="error", iteration=iteration, data=data))


def _named_outputs_required(skill: SkillConfig) -> bool:
    if not skill.outputs:
        return False
    if skill.kind == "script":
        return True
    if skill.kind == "agent":
        return uses_emit_output(skill.outputs)
    if not skill.steps:
        return False
    last = skill.steps[-1]
    if last.type == "script":
        return True
    if last.type in ("llm", "skill"):
        return uses_emit_output(skill.outputs)
    return False


def _output_persist_keys(
    skill: SkillConfig, artifacts: dict[str, ArtifactValue], primary_text: str
) -> list[str]:
    artifact_keys = list(artifacts)
    declared_keys = [item.key for item in skill.outputs]
    if declared_keys and set(declared_keys) == set(artifact_keys):
        return declared_keys
    if primary_text:
        for key in artifact_keys:
            # ``_value_as_text`` (not ``==``) so a collection value (list)
            # compares against the joined primary text instead of always
            # failing the equality check.
            if _value_as_text(artifacts[key]) == primary_text:
                return [key] + [item for item in artifact_keys if item != key]
    return artifact_keys


def _collection_document_count(
    skill: SkillConfig, artifacts: dict[str, ArtifactValue], primary_text: str
) -> int:
    """Count of documents ``persist_run_outputs`` would create for this
    result, without allocating anything on disk.

    Mirrors the ``items`` construction in :func:`persist_run_outputs`
    (one document per plain key, one per element of a ``multiple`` key's
    list). Used to enforce ``MAX_COLLECTION_DOCUMENTS`` in "на экран" mode
    too, not only when ``persist=True`` — ADR-0025 Decision 5 requires the
    run itself to finish ``failed`` with an explicit reason, not just the
    later ``POST /runs/{id}/save``.
    """
    declared = {item.key: item for item in skill.outputs}
    persist_keys = _output_persist_keys(skill, artifacts, primary_text)
    if not persist_keys:
        return 1
    count = 0
    for key in persist_keys:
        item = declared.get(key)
        value = artifacts[key]
        if item is not None and item.multiple and isinstance(value, list):
            count += len(value)
        else:
            count += 1
    return count


def _ordered_artifacts(
    skill: SkillConfig, artifacts: dict[str, ArtifactValue]
) -> dict[str, ArtifactValue]:
    if not artifacts:
        return {}
    declared = [item.key for item in skill.outputs if item.key in artifacts]
    leftover = [
        key for key in artifacts if key not in {item.key for item in skill.outputs}
    ]
    return {key: artifacts[key] for key in declared + leftover}


def _collection_counts_note(
    skill: SkillConfig, artifacts: dict[str, ArtifactValue]
) -> str:
    """"; collected: key=N, ..." for every declared ``multiple`` key so a
    ``capped`` failure while an agent skill was mid-collection reports how
    many elements it had already accumulated, instead of just a missing/empty
    key name."""
    counts = [
        f"{item.key}={len(artifacts.get(item.key) or [])}"
        for item in skill.outputs
        if item.multiple
    ]
    return "; collected: " + ", ".join(counts) if counts else ""


def _verify_retry_content(failures: list[str]) -> str:
    return "verify failed: " + "; ".join(failures) + ". Исправь и повтори."


def _primary_result_title(skill: SkillConfig, docs: list) -> str:
    if not docs:
        return f"{skill.name} — результат"
    if len(docs) == 1:
        return f"{skill.name} — {docs[0].title}"
    return f"{skill.name} — {docs[0].title} (+{len(docs) - 1})"


# ADR-0025 (Decision 7): a collection element's title is its first markdown
# heading line, if present; otherwise a positional fallback.
_MD_HEADING_RE = re.compile(r"^#{1,6}[ \t]+(.+?)\s*$", re.MULTILINE)


def _first_markdown_heading(text: str) -> str | None:
    match = _MD_HEADING_RE.search(text)
    if match is None:
        return None
    heading = match.group(1).strip()
    return heading or None


def _collection_item_title(
    skill: SkillConfig, item: SkillOutput | None, key: str, text: str, position: int
) -> str:
    heading = _first_markdown_heading(text)
    if heading:
        return heading
    description = item.description if item is not None else key
    return f"{skill.name} — {description} {position + 1}"


def persist_run_outputs(
    db: Database,
    workspace_dir: str,
    *,
    skill: SkillConfig,
    docs: list,
    session_id: str | None,
    primary_text: str,
    artifacts: dict[str, ArtifactValue],
    primary_title: str | None = None,
) -> tuple[str, list[str], str, dict[str, ArtifactValue]]:
    workspace_path = Path(workspace_dir)
    title = primary_title or _primary_result_title(skill, docs)
    items: list[tuple[str, str, str]] = []
    declared = {item.key: item for item in skill.outputs}
    persist_keys = _output_persist_keys(skill, artifacts, primary_text)
    if persist_keys:
        for index, key in enumerate(persist_keys):
            item = declared.get(key)
            value = artifacts[key]
            if item is not None and item.multiple:
                # ADR-0025 (Decision 2/7): a collection key expands into N
                # documents, one per element. Every element — including the
                # first element of the first persist key — titles itself
                # from its own first markdown heading, else a positional
                # fallback; there is no run-level-title exception for
                # element 0 (a pure ``multiple`` primary must not name its
                # first chapter after the input document).
                elements = value if isinstance(value, list) else [value]
                for pos, element_text in enumerate(elements):
                    item_title = _collection_item_title(
                        skill, item, key, element_text, pos
                    )
                    items.append((key, item_title, element_text))
            else:
                # Defensive: a stale/undeclared key from an earlier run may
                # still carry a list value — collapse it to text instead of
                # writing a non-string as a document body.
                text = _value_as_text(value) if isinstance(value, list) else value
                if index == 0:
                    item_title = title
                elif item is not None:
                    item_title = f"{skill.name} — {item.description}"
                else:
                    item_title = f"{skill.name} — {key}"
                items.append((key, item_title, text))
    else:
        items.append(("", title, primary_text))

    if len(items) > MAX_COLLECTION_DOCUMENTS:
        # ADR-0025 (Decision 5): checked before any allocate_rel_path/touch
        # below so an over-limit run leaves no partial output on disk.
        raise CollectionLimitError(
            f"too many output documents: {len(items)} "
            f"(max {MAX_COLLECTION_DOCUMENTS})"
        )

    allocated: list[tuple[str, str, str, str]] = []
    try:
        for key, item_title, text in items:
            rel_path = allocate_rel_path(
                workspace_path,
                safe_filename(item_title, ".md"),
                subdir="results",
            )
            dest = workspace_path / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.touch()
            allocated.append((key, item_title, text, rel_path))

        stems = [Path(rel_path).stem for *_, rel_path in allocated]
        keys_by_index = [key for key, *_ in allocated]
        input_stems = [Path(doc.path).stem for doc in docs]
        title_map = build_title_to_stem_map(db)
        prepared: list[tuple[str, str, str, str, str]] = []
        rewritten_primary = primary_text
        rewritten_artifacts: dict[str, ArtifactValue] = {}
        for index, (_key, item_title, text, rel_path) in enumerate(allocated):
            # ADR-0025 (Consequences: wiki-links): a collection element links
            # only to the other top-level results (primary + companions),
            # never to its own peer elements — exclude same-key siblings, not
            # just self.
            sibling_stems = [
                stem
                for i, stem in enumerate(stems)
                if i != index and (not _key or keys_by_index[i] != _key)
            ]
            file_text = rewrite_wiki_links(text, title_map)
            file_text = ensure_parent_wikilinks(
                file_text, input_stems + sibling_stems
            )
            dest = workspace_path / rel_path
            dest.write_text(file_text, encoding="utf-8")
            out_id = uuid.uuid4().hex
            prepared.append((_key, item_title, file_text, rel_path, out_id))
            if _key:
                key_item = declared.get(_key)
                if key_item is not None and key_item.multiple:
                    bucket = rewritten_artifacts.get(_key)
                    if not isinstance(bucket, list):
                        bucket = []
                        rewritten_artifacts[_key] = bucket
                    bucket.append(file_text)
                else:
                    rewritten_artifacts[_key] = file_text
            if index == 0:
                rewritten_primary = file_text

        if persist_keys:
            primary_key = persist_keys[0]
            primary_item = declared.get(primary_key)
            if primary_item is not None and primary_item.multiple:
                primary_value = rewritten_artifacts.get(primary_key)
                if isinstance(primary_value, list) and primary_value:
                    rewritten_primary = _value_as_text(primary_value)

        doc_ids = [out_id for *_, out_id in prepared]
        with db.connect() as conn:
            for _key, item_title, file_text, rel_path, out_id in prepared:
                dest = workspace_path / rel_path
                st = dest.stat()
                create_document(
                    db,
                    title=item_title,
                    path=rel_path,
                    kind="result_md",
                    doc_id=out_id,
                    mtime=st.st_mtime,
                    size=st.st_size,
                    content_hash=content_hash_bytes(file_text.encode("utf-8")),
                    conn=conn,
                )
            if session_id is not None and doc_ids:
                attach_documents(db, session_id, doc_ids, conn=conn)
        return doc_ids[0], doc_ids, rewritten_primary, rewritten_artifacts
    except Exception:
        for *_, rel_path in allocated:
            dest = workspace_path / rel_path
            dest.unlink(missing_ok=True)
        raise


def _config_hash(skill: SkillConfig) -> str:
    return hashlib.sha256(skill.to_json().encode("utf-8")).hexdigest()[:16]


def _step_input_texts(value: PipelineValue) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _nested_verify_failures(trace: Trace) -> list[str]:
    failures: list[str] = []
    for entry in trace.entries:
        if entry.kind == "verify" and not entry.data.get("passed", True):
            failures.extend(str(item) for item in (entry.data.get("failures") or []))
    return failures


def _deadline_reached(trace: Trace, iteration: int) -> bool:
    if not nested_deadline_exceeded():
        return False
    trace.entries.append(
        TraceEntry("deadline", iteration, {"error": "deadline exceeded"})
    )
    return True


def _with_step_id(event: AgentEvent, step_id: str) -> AgentEvent:
    if hasattr(event, "step_id"):
        return replace(event, step_id=step_id)
    return event


# A skill step runs a whole nested skill, so the live stream carries only the
# bookends (call → result); the nested run has its own trace behind ``run_id``.
_SKILL_STEP_INPUT_PREVIEW = 400


def _skill_step_call_event(
    step: PipelineStep, name: str, step_input: PipelineValue
) -> ToolCallEvent:
    preview = _value_as_text(step_input)
    if len(preview) > _SKILL_STEP_INPUT_PREVIEW:
        preview = preview[:_SKILL_STEP_INPUT_PREVIEW] + "…"
    return ToolCallEvent(
        id=f"step-{step.id}",
        name=name,
        arguments={"text": preview},
        step_id=step.id,
    )


def _skill_step_result_event(
    step: PipelineStep, name: str, ok: bool, payload: dict
) -> ToolResultEvent:
    return ToolResultEvent(
        id=f"step-{step.id}",
        name=name,
        ok=ok,
        result=payload,
        step_id=step.id,
    )


def _pipeline_step_input(
    step: PipelineStep,
    current: PipelineValue | None,
    doc_texts: list[str],
) -> PipelineValue:
    if step.input == "documents":
        return doc_texts[0] if len(doc_texts) == 1 else list(doc_texts)
    if step.input == "previous":
        if current is None:
            raise ValueError(
                f"pipeline step {step.id!r} input is 'previous' "
                "but there is no previous result"
            )
        return current
    raise ValueError(
        f"pipeline step {step.id!r}: unknown input {step.input!r}"
    )


def _pipeline_llm_user_content(
    *,
    step_input: PipelineValue,
    from_documents: bool,
    docs: list,
    input_doc_ids: list[str],
    doc_texts: list[str],
) -> str:
    if from_documents and docs:
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
    run_id: str | None = None
    output_doc_ids: list[str] | None = None
    result_artifacts: dict[str, ArtifactValue] | None = None


@dataclass
class _ApplyOutcome:
    """Mutable holder so the shared core can report status/doc_id to collectors."""

    output_doc_id: str | None = None
    status: str = "failed"
    result_text: str | None = None
    run_id: str | None = None
    output_doc_ids: list[str] | None = None
    result_artifacts: dict[str, ArtifactValue] | None = None


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
    providers: dict[str, LLMProvider] | None = None,
    input_texts: list[str] | None = None,
    parent_run_id: str | None = None,
    fallback_model: str = "",
    call_context: SkillCallContext | None = None,
    budget: SkillBudget | None = None,
    max_skill_depth: int = 2,
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

    ADR-0019: ``input_texts`` supplies raw text inputs without document rows
    (nested skill-as-tool). When set, documents are not loaded.

    CATALOG-56: ``user_prompt`` is an optional runtime clarification appended
    to the agent start user message; script skills ignore it.
    """
    texts_mode = input_texts is not None
    docs = []
    if texts_mode:
        doc_texts = [t if isinstance(t, str) else str(t) for t in (input_texts or [])]
        if not doc_texts:
            raise ValueError("apply requires at least one input text")
        if skill.input_arity is not None and len(doc_texts) != skill.input_arity:
            raise ValueError(
                f"skill expects {skill.input_arity} input document(s), "
                f"got {len(doc_texts)}"
            )
    else:
        if not input_doc_ids:
            raise ValueError("apply requires at least one input document")
        for doc_id in input_doc_ids:
            d = get_document(db, doc_id)
            if d is None:
                raise ValueError(f"input document not found: {doc_id}")
            docs.append(d)

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
    emit_artifacts: dict[str, ArtifactValue] = {}
    if skill.kind == "agent" and uses_emit_output(skill.outputs):
        register_emit_output(tools, skill.outputs, emit_artifacts)

    if not texts_mode:
        doc_texts = [
            extract_text(str(Path(workspace_dir) / d.path), d.kind) for d in docs
        ]

    # 3. Create the skill_run row (or reuse a pre-created one).
    if run_id is None:
        run_id = create_run(
            db,
            skill_id=skill_id,
            session_id=session_id,
            input_doc_ids=input_doc_ids if not texts_mode else [],
            persist=persist,
            user_prompt=runtime_prompt,
            parent_run_id=parent_run_id,
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

    outcome.run_id = run_id
    if parent_run_id is not None:
        pinned = _config_hash(skill)
        trace.entries.append(
            TraceEntry(
                kind="skill_pin",
                iteration=0,
                data={
                    "skill_id": skill_id,
                    "config_hash": pinned,
                    "parent_run_id": parent_run_id,
                    "depth": 0 if call_context is None else call_context.depth,
                },
            )
        )

    logger.info(
        "apply_skill start skill=%s skill_id=%s input_docs=%d run_id=%s",
        skill.name,
        skill_id,
        len(doc_texts),
        run_id,
    )

    last_text: str | None = None
    last_artifacts: dict[str, ArtifactValue] = {}
    last_capped = False
    passed = False
    deadline_stopped = False
    collection_limit_exceeded = False
    # Attempt number surfaced in a later _record_outputs_error call for the
    # collection-limit check (shared tail, all skill.kind values): 1 for
    # script (single deterministic attempt), the step count for pipeline,
    # the current retry for agent — set inside each branch below.
    outputs_attempt = 1
    pipeline_halted = False
    output_doc_id: str | None = None
    output_doc_ids: list[str] = []
    verify_model = skill.model or fallback_model
    verify_provider = provider_for_skill(providers, provider, skill.provider)
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
            # CATALOG-3/16: surface script execution as granular trace steps
            # (start/done/error with a code snippet, the return value and the
            # wall-clock duration) so a script run is not an opaque black box.
            script_start = ScriptEvent(stage="start", snippet=skill.code)
            yield script_start
            log_agent_event(script_start)
            t0 = time.perf_counter()
            outputs_failed = False
            try:
                raw = await run_skill_script_async(skill.code, doc_texts)
                text, last_artifacts = _finalize_script_result(skill, raw)
            except NamedOutputsError as exc:
                script_error = ScriptEvent(
                    stage="error", error=str(exc), duration=time.perf_counter() - t0
                )
                yield script_error
                log_agent_event(script_error)
                _record_outputs_error(trace, 1, str(exc))
                last_text = None
                last_artifacts = {}
                passed = False
                outputs_failed = True
                text = ""
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
            if not outputs_failed:
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
                if text:
                    yield TokenEvent(delta=text)
                if _deadline_reached(trace, 1):
                    deadline_stopped = True
                    last_capped = True
                else:
                    result = await run_verify_async(
                        text or "",
                        skill.verify_checks,
                        db=db,
                        provider=verify_provider,
                        model=verify_model,
                    )
                    verify_event = VerifyEvent(iteration=1, result=result)
                    yield verify_event
                    log_agent_event(verify_event)
                    trace.entries.append(
                        TraceEntry(
                            kind="verify",
                            iteration=1,
                            data=result.as_payload(),
                        )
                    )
                    passed = result.passed
        elif skill.kind == "pipeline":
            current: PipelineValue | None = None
            outputs_attempt = max(len(skill.steps), 1)
            for index, step in enumerate(skill.steps):
                if _deadline_reached(trace, index + 1):
                    deadline_stopped = True
                    last_capped = True
                    break
                step_input = _pipeline_step_input(step, current, doc_texts)
                from_documents = step.input == "documents"
                if step.type == "script":
                    script_start = ScriptEvent(
                        stage="start", snippet=step.code, step_id=step.id
                    )
                    yield script_start
                    log_agent_event(script_start)
                    t0 = time.perf_counter()
                    try:
                        raw = await run_skill_script_async(
                            step.code, _value_as_documents(step_input)
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
                    is_last = index == len(skill.steps) - 1
                    if isinstance(raw, dict) and not is_last:
                        message = (
                            f"pipeline step {step.id!r} returned a dict; "
                            "named outputs are only allowed on the last step"
                        )
                        script_error = ScriptEvent(
                            stage="error",
                            error=message,
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
                                    "outputs": True,
                                    "error": message,
                                    "step_id": step.id,
                                },
                            )
                        )
                        raise PipelineStepError(message)
                    if is_last:
                        try:
                            display, last_artifacts = _finalize_script_result(
                                skill, raw
                            )
                        except NamedOutputsError as exc:
                            script_error = ScriptEvent(
                                stage="error",
                                error=str(exc),
                                duration=time.perf_counter() - t0,
                                step_id=step.id,
                            )
                            yield script_error
                            log_agent_event(script_error)
                            _record_outputs_error(
                                trace, index + 1, str(exc), step.id
                            )
                            last_text = None
                            last_artifacts = {}
                            passed = False
                            pipeline_halted = True
                            break
                        current = display
                    else:
                        display = _value_as_text(raw)
                        current = raw
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
                    last_text = display
                elif step.type == "llm":
                    step_tools = base_tools.filter(
                        ensure_read_document_tool(step.allowed_tools)
                    )
                    is_last = index == len(skill.steps) - 1
                    step_emits = is_last and uses_emit_output(skill.outputs)
                    step_artifacts: dict[str, ArtifactValue] = {}
                    if step_emits:
                        register_emit_output(
                            step_tools, skill.outputs, step_artifacts
                        )
                    start_content = _pipeline_llm_user_content(
                        step_input=step_input,
                        from_documents=from_documents,
                        docs=docs,
                        input_doc_ids=input_doc_ids,
                        doc_texts=doc_texts,
                    )
                    if runtime_prompt is not None:
                        start_content = (
                            f"{start_content}\n\nУточнение к заданию:\n"
                            f"{runtime_prompt}"
                        )
                    if step_emits:
                        start_content = (
                            f"{start_content}{named_outputs_prompt(skill.outputs)}"
                        )
                    messages: list[Message] = [
                        Message(role="user", content=start_content)
                    ]
                    step_provider = provider_for_skill(
                        providers, provider, step.provider or skill.provider
                    )
                    llm_attempts = skill.max_retries + 1 if step_emits else 1
                    for llm_try in range(llm_attempts):
                        # See the matching comment in the agent branch above:
                        # a ``multiple`` key's bucket accumulates across
                        # calls, so it must be dropped before each retry
                        # re-runs the exchange or the retry's re-emission
                        # duplicates the previous attempt's elements. Plain
                        # keys are left as-is (they overwrite on re-emission
                        # and may legitimately carry over unchanged).
                        if step_emits:
                            for _item in skill.outputs:
                                if _item.multiple:
                                    step_artifacts.pop(_item.key, None)
                        text = None
                        capped = False
                        before = len(trace.entries)
                        async for event in _run_agent_core(
                            provider=step_provider,
                            model=step.model or skill.model or fallback_model,
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
                                if event.finish_reason == "deadline":
                                    deadline_stopped = True
                        for entry in trace.entries[before:]:
                            entry.data["step_id"] = step.id
                        if step_emits:
                            last_artifacts = _ordered_artifacts(
                                skill, step_artifacts
                            )
                            last_text = primary_output_text(
                                skill.outputs, step_artifacts, text
                            )
                            current = last_text or ""
                        else:
                            current = text or ""
                            last_text = current
                        if deadline_stopped:
                            last_capped = True
                            break
                        if not step_emits:
                            if is_last:
                                last_capped = capped
                            break
                        output_failures = named_output_failures(
                            skill.outputs, step_artifacts
                        )
                        if not output_failures:
                            last_capped = capped
                            break
                        result = VerifyResult(
                            passed=False, failures=output_failures, checks=[]
                        )
                        verify_event = VerifyEvent(
                            iteration=llm_try + 1, result=result
                        )
                        yield verify_event
                        log_agent_event(verify_event)
                        trace.entries.append(
                            TraceEntry(
                                kind="verify",
                                iteration=llm_try + 1,
                                data=result.as_payload(),
                            )
                        )
                        if capped or llm_try >= skill.max_retries:
                            reason = "; ".join(output_failures)
                            if capped:
                                last_capped = True
                                reason = "capped: " + reason + _collection_counts_note(
                                    skill, step_artifacts
                                )
                            _record_outputs_error(
                                trace, index + 1, reason, step.id
                            )
                            pipeline_halted = True
                            break
                        messages.append(
                            Message(role="assistant", content=text or "")
                        )
                        messages.append(
                            Message(
                                role="user",
                                content=_verify_retry_content(output_failures),
                            )
                        )
                    if deadline_stopped or pipeline_halted:
                        break
                elif step.type == "skill":
                    nested_skill = step.config
                    if nested_skill is None:
                        raise ValueError(
                            f"pipeline step {step.id!r}: skill snapshot is missing"
                        )
                    nested_id = step.skill_id or nested_skill.name
                    nested_name = step.skill_name or nested_skill.name
                    nested_hash = step.config_hash or _config_hash(nested_skill)
                    current_depth = (
                        0 if call_context is None else call_context.depth
                    )
                    nested_ctx = (call_context or SkillCallContext()).nested(
                        nested_id
                    )
                    call_event = _skill_step_call_event(
                        step, nested_name, step_input
                    )
                    yield call_event
                    log_agent_event(call_event)
                    if current_depth >= max_skill_depth:
                        message = (
                            f"pipeline step {step.id!r}: max skill depth "
                            f"exceeded ({current_depth} >= {max_skill_depth})"
                        )
                        trace.entries.append(
                            TraceEntry(
                                kind="error",
                                iteration=index + 1,
                                data={
                                    "step_id": step.id,
                                    "error": message,
                                    "skill_name": nested_name,
                                    "config_hash": nested_hash,
                                    "depth": nested_ctx.depth,
                                },
                            )
                        )
                        depth_event = _skill_step_result_event(
                            step,
                            nested_name,
                            False,
                            {
                                "error": message,
                                "skill_id": nested_id,
                                "skill_name": nested_name,
                                "config_hash": nested_hash,
                                "depth": nested_ctx.depth,
                            },
                        )
                        yield depth_event
                        log_agent_event(depth_event)
                        raise PipelineStepError(message)
                    step_budget = current_skill_budget(budget)
                    already_held = skill_hold_active()
                    hold = None
                    if step_budget is not None:
                        if step_budget.mark_deadline_if_exceeded():
                            trace.entries.append(
                                TraceEntry(
                                    kind="deadline",
                                    iteration=index + 1,
                                    data={
                                        "error": "deadline exceeded",
                                        "step_id": step.id,
                                        "skill_name": nested_name,
                                        "depth": nested_ctx.depth,
                                    },
                                )
                            )
                            deadline_event = _skill_step_result_event(
                                step,
                                nested_name,
                                False,
                                {
                                    "error": "deadline exceeded",
                                    "skill_id": nested_id,
                                    "skill_name": nested_name,
                                    "depth": nested_ctx.depth,
                                },
                            )
                            yield deadline_event
                            log_agent_event(deadline_event)
                            deadline_stopped = True
                            last_capped = True
                            break
                        if already_held:
                            needed_llm, needed_runs = 0, 1
                        else:
                            needed_llm, needed_runs = estimate_skill_budget(
                                nested_skill
                            )
                        hold = step_budget.reserve(needed_llm, needed_runs)
                        if hold is None:
                            trace.entries.append(
                                TraceEntry(
                                    kind="budget",
                                    iteration=index + 1,
                                    data={
                                        "error": "budget exhausted",
                                        "step_id": step.id,
                                        "skill_name": nested_name,
                                        "config_hash": nested_hash,
                                        "depth": nested_ctx.depth,
                                        "llm_calls_left": step_budget.llm_calls_left,
                                        "nested_runs_left": step_budget.nested_runs_left,
                                        "needed_llm_calls": needed_llm,
                                        "needed_nested_runs": needed_runs,
                                    },
                                )
                            )
                            budget_event = _skill_step_result_event(
                                step,
                                nested_name,
                                False,
                                {
                                    "error": "budget exhausted",
                                    "skill_id": nested_id,
                                    "skill_name": nested_name,
                                    "config_hash": nested_hash,
                                    "depth": nested_ctx.depth,
                                    "budget": {
                                        "llm_calls_left": step_budget.llm_calls_left,
                                        "nested_runs_left": (
                                            step_budget.nested_runs_left
                                        ),
                                        "needed_llm_calls": needed_llm,
                                        "needed_nested_runs": needed_runs,
                                    },
                                },
                            )
                            yield budget_event
                            log_agent_event(budget_event)
                            last_capped = True
                            pipeline_halted = True
                            break
                    nested_tools = build_document_tools(
                        db, workspace_dir, session_id
                    )
                    try:
                        with nested_skill_hold(
                            None if already_held else hold,
                            None if already_held else step_budget,
                        ):
                            nested_result = await apply_nested_skill_collect(
                                provider=provider,
                                db=db,
                                workspace_dir=workspace_dir,
                                skill=nested_skill,
                                skill_id=nested_id,
                                base_tools=nested_tools,
                                session_id=session_id,
                                input_texts=_step_input_texts(step_input),
                                parent_run_id=run_id,
                                fallback_model=fallback_model,
                                providers=providers,
                                call_context=nested_ctx,
                                budget=step_budget,
                                max_skill_depth=max_skill_depth,
                            )
                    except Exception as exc:
                        trace.entries.append(
                            TraceEntry(
                                kind="error",
                                iteration=index + 1,
                                data={
                                    "step_id": step.id,
                                    "error": str(exc),
                                    "skill": True,
                                    "skill_name": nested_name,
                                    "depth": nested_ctx.depth,
                                },
                            )
                        )
                        failed_event = _skill_step_result_event(
                            step,
                            nested_name,
                            False,
                            {
                                "error": str(exc),
                                "skill_id": nested_id,
                                "skill_name": nested_name,
                                "depth": nested_ctx.depth,
                            },
                        )
                        yield failed_event
                        log_agent_event(failed_event)
                        raise
                    finally:
                        if step_budget is not None and hold is not None:
                            step_budget.release(hold)
                    verify_failures = _nested_verify_failures(
                        nested_result.trace
                    )
                    nested_ok = nested_result.status == "ok"
                    step_payload = {
                        "ok": nested_ok,
                        "status": nested_result.status,
                        "run_id": nested_result.run_id,
                        "skill_id": nested_id,
                        "skill_name": nested_name,
                        "config_hash": nested_hash,
                        "depth": nested_ctx.depth,
                    }
                    trace.entries.append(
                        TraceEntry(
                            kind="tool_result",
                            iteration=index + 1,
                            data={
                                "name": nested_name,
                                "ok": nested_ok,
                                "step_id": step.id,
                                "run_id": nested_result.run_id,
                                "skill_id": nested_id,
                                "skill_name": nested_name,
                                "config_hash": nested_hash,
                                "depth": nested_ctx.depth,
                                "failures": verify_failures,
                                "result": {
                                    **step_payload,
                                    "verify_failures": verify_failures,
                                },
                            },
                        )
                    )
                    result_event = _skill_step_result_event(
                        step, nested_name, nested_ok, step_payload
                    )
                    yield result_event
                    log_agent_event(result_event)
                    current = nested_result.result_text or ""
                    last_text = current
                    if nested_result.status != "ok":
                        pipeline_halted = True
                        break
                else:
                    raise ValueError(
                        f"unknown pipeline step type: {step.type!r}"
                    )
            if not deadline_stopped and not pipeline_halted and _deadline_reached(
                trace, max(len(skill.steps), 1)
            ):
                deadline_stopped = True
                last_capped = True
            if (
                not deadline_stopped
                and not pipeline_halted
                and _named_outputs_required(skill)
                and not last_artifacts
            ):
                message = (
                    "skill declared outputs but the last pipeline step "
                    "did not produce them"
                )
                _record_outputs_error(trace, max(len(skill.steps), 1), message)
                last_text = None
                last_artifacts = {}
                passed = False
                pipeline_halted = True
            if not deadline_stopped and not pipeline_halted:
                final_text = last_text or ""
                if last_text:
                    yield TokenEvent(delta=last_text)
                result = await run_verify_async(
                    final_text,
                    skill.verify_checks,
                    db=db,
                    provider=verify_provider,
                    model=verify_model,
                )
                verify_event = VerifyEvent(iteration=1, result=result)
                yield verify_event
                log_agent_event(verify_event)
                trace.entries.append(
                    TraceEntry(
                        kind="verify",
                        iteration=1,
                        data=result.as_payload(),
                    )
                )
                passed = result.passed
        else:
            # ---- Agent path (ADR-0001/0002) ----
            # Build the start message listing every input document (CATALOG-4).
            if texts_mode:
                start_content = _pipeline_llm_user_content(
                    step_input=doc_texts[0] if len(doc_texts) == 1 else list(doc_texts),
                    from_documents=False,
                    docs=docs,
                    input_doc_ids=input_doc_ids,
                    doc_texts=doc_texts,
                )
            else:
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
            if uses_emit_output(skill.outputs):
                start_content = f"{start_content}{named_outputs_prompt(skill.outputs)}"
            user_msg = Message(role="user", content=start_content)
            messages: list[Message] = [user_msg]
            run_provider = provider_for_skill(providers, provider, skill.provider)
            run_model = skill.model or fallback_model

            # max_retries = number of retries after the first attempt.
            for r in range(skill.max_retries + 1):
                # ``register_emit_output`` accumulates a ``multiple`` key by
                # appending to a list (emit_output.py) rather than
                # overwriting, so a stale bucket from a failed attempt must
                # be dropped before the retry re-runs the whole exchange —
                # otherwise the retry's re-emission stacks on top of the
                # previous attempt's elements instead of replacing them
                # (silent duplicate documents on persist). Plain (non-
                # ``multiple``) keys are intentionally left in place: they
                # overwrite on re-emission already, and a retry's model
                # reply commonly re-sends only the key(s) verify flagged,
                # relying on an already-satisfied plain key to carry over.
                for _item in skill.outputs:
                    if _item.multiple:
                        emit_artifacts.pop(_item.key, None)
                text: str | None = None
                capped = False
                # Drive the agent loop directly: forward each inner event to the
                # stream and capture the final text/capped from its FinishEvent,
                # while _run_agent_core appends to our shared ``trace``.
                async for event in _run_agent_core(
                    provider=run_provider,
                    model=run_model,
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
                        if event.finish_reason == "deadline":
                            deadline_stopped = True

                last_text = text
                last_capped = capped
                outputs_attempt = r + 1
                agent_emits = uses_emit_output(skill.outputs)
                if agent_emits:
                    last_artifacts = _ordered_artifacts(skill, emit_artifacts)
                    last_text = primary_output_text(
                        skill.outputs, emit_artifacts, text
                    )
                if last_text:
                    yield TokenEvent(delta=last_text)
                if deadline_stopped:
                    break
                if _deadline_reached(trace, r + 1):
                    deadline_stopped = True
                    last_capped = True
                    break

                output_failures = (
                    named_output_failures(skill.outputs, emit_artifacts)
                    if agent_emits
                    else []
                )
                if output_failures:
                    result = VerifyResult(
                        passed=False, failures=output_failures, checks=[]
                    )
                else:
                    result = await run_verify_async(
                        last_text or "",
                        skill.verify_checks,
                        db=db,
                        provider=verify_provider,
                        model=verify_model,
                    )
                verify_event = VerifyEvent(iteration=r + 1, result=result)
                yield verify_event
                log_agent_event(verify_event)
                trace.entries.append(
                    TraceEntry(
                        kind="verify",
                        iteration=r + 1,
                        data=result.as_payload(),
                    )
                )

                if result.passed:
                    passed = True
                    break

                if agent_emits and capped and output_failures:
                    reason = (
                        "capped: "
                        + "; ".join(output_failures)
                        + _collection_counts_note(skill, emit_artifacts)
                    )
                    _record_outputs_error(trace, r + 1, reason)
                    break

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
                            content=_verify_retry_content(list(result.failures)),
                        )
                    )

        # 5. Persist result on success (CATALOG-18: only in "persist" mode —
        # "preview" mode leaves the result on screen, materialized later via
        # POST /runs/{id}/save if the user chooses to). Either way, the
        # collection-document cap is enforced here, not only inside
        # persist_run_outputs — ADR-0025 Decision 5 requires the run itself
        # to finish failed with an explicit reason, so a "на экран" run must
        # not look successful only to have the refusal surface later as a
        # 409 from the save endpoint with nothing left to recover. ``docs``
        # empty means a nested skill-as-tool call (ADR-0019 texts_mode),
        # which never persists and passes its result up as text, not
        # documents — the cap does not apply there.
        if passed and docs:
            try:
                if persist:
                    output_doc_id, output_doc_ids, last_text, last_artifacts = (
                        persist_run_outputs(
                            db,
                            workspace_dir,
                            skill=skill,
                            docs=docs,
                            session_id=session_id,
                            primary_text=last_text or "",
                            artifacts=last_artifacts,
                        )
                    )
                    logger.info(
                        "apply_skill persisted output_doc_id=%s", output_doc_id
                    )
                else:
                    doc_count = _collection_document_count(
                        skill, last_artifacts, last_text or ""
                    )
                    if doc_count > MAX_COLLECTION_DOCUMENTS:
                        raise CollectionLimitError(
                            f"too many output documents: {doc_count} "
                            f"(max {MAX_COLLECTION_DOCUMENTS})"
                        )
            except CollectionLimitError as exc:
                # Fail-closed. ``result_text``/``result_artifacts`` are kept
                # (not wiped) so the already-computed result can still be
                # inspected — matches the invariant a few lines below that
                # result_text is stored regardless of persist. A persist-mode
                # failure here rolled back before any file was written; a
                # preview-mode failure never wrote anything to begin with.
                _record_outputs_error(trace, outputs_attempt, str(exc))
                passed = False
                collection_limit_exceeded = True
                output_doc_id = None
                output_doc_ids = []

        status = "ok" if passed else "failed"
        stored_artifacts = last_artifacts or None
        stored_doc_ids = output_doc_ids or None

        # 6. Record outcome (normal path). ``result_text`` is stored
        # regardless of ``persist`` so a preview run can still be saved later.
        finish_run(
            db,
            run_id,
            status=status,
            output_doc_id=output_doc_id,
            trace=trace,
            result_text=last_text,
            result_artifacts=stored_artifacts,
            output_doc_ids=stored_doc_ids,
        )
        done = True

        outcome.output_doc_id = output_doc_id
        outcome.output_doc_ids = stored_doc_ids
        outcome.status = status
        outcome.result_text = last_text
        outcome.result_artifacts = stored_artifacts

        logger.info(
            "apply_skill done status=%s output_doc_id=%s", status, output_doc_id
        )

        # 7. Emit finish.
        if deadline_stopped:
            apply_reason = "deadline"
        elif passed:
            apply_reason = "stop"
        elif collection_limit_exceeded:
            apply_reason = "collection_limit"
        elif last_capped:
            apply_reason = "capped"
        else:
            apply_reason = "verify_failed"
        finish_apply = FinishEvent(
            text=last_text,
            finish_reason=apply_reason,
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
                result_artifacts=_ordered_artifacts(
                    skill, emit_artifacts or last_artifacts
                )
                or None,
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
                result_artifacts=_ordered_artifacts(
                    skill, emit_artifacts or last_artifacts
                )
                or None,
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
                result_artifacts=_ordered_artifacts(
                    skill, emit_artifacts or last_artifacts
                )
                or None,
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
    providers: dict[str, LLMProvider] | None = None,
    input_texts: list[str] | None = None,
    parent_run_id: str | None = None,
    fallback_model: str = "",
    call_context: SkillCallContext | None = None,
    budget: SkillBudget | None = None,
    max_skill_depth: int = 2,
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
        providers=providers,
        input_texts=input_texts,
        parent_run_id=parent_run_id,
        fallback_model=fallback_model,
        call_context=call_context,
        budget=budget,
        max_skill_depth=max_skill_depth,
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
    providers: dict[str, LLMProvider] | None = None,
    input_texts: list[str] | None = None,
    parent_run_id: str | None = None,
    fallback_model: str = "",
    call_context: SkillCallContext | None = None,
    budget: SkillBudget | None = None,
    max_skill_depth: int = 2,
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
        providers=providers,
        input_texts=input_texts,
        parent_run_id=parent_run_id,
        fallback_model=fallback_model,
        call_context=call_context,
        budget=budget,
        max_skill_depth=max_skill_depth,
    ):
        pass
    return ApplyResult(
        output_doc_id=outcome.output_doc_id,
        status=outcome.status,
        result_text=outcome.result_text,
        trace=trace,
        run_id=outcome.run_id,
        output_doc_ids=outcome.output_doc_ids,
        result_artifacts=outcome.result_artifacts,
    )


async def apply_nested_skill_collect(
    *,
    provider: LLMProvider,
    db: Database,
    workspace_dir: str,
    skill: SkillConfig,
    skill_id: str,
    base_tools: ToolRegistry,
    session_id: str | None,
    input_texts: list[str],
    parent_run_id: str,
    fallback_model: str = "",
    providers: dict[str, LLMProvider] | None = None,
    call_context: SkillCallContext | None = None,
    budget: SkillBudget | None = None,
    max_skill_depth: int = 2,
) -> ApplyResult:
    return await apply_skill_collect(
        provider=provider,
        db=db,
        workspace_dir=workspace_dir,
        skill=skill,
        skill_id=skill_id,
        input_doc_ids=[],
        base_tools=base_tools,
        session_id=session_id,
        persist=False,
        providers=providers,
        input_texts=input_texts,
        parent_run_id=parent_run_id,
        fallback_model=fallback_model,
        call_context=call_context,
        budget=budget,
        max_skill_depth=max_skill_depth,
    )
