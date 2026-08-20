from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from catalog.agent.registry import ToolRegistry
from catalog.documents.extract import extract_text
from catalog.llm.base import ToolSpec
from catalog.skills.budget import SkillBudget, consume_script_try
from catalog.skills.config import (
    MAX_SKILL_OUTPUTS,
    PIPELINE_STEP_INPUTS,
    PIPELINE_STEP_TYPES,
    SKILL_KINDS,
    PipelineStep,
    SkillOutput,
    VerifyCheck,
    parse_skill_outputs,
    pipeline_step_to_dict,
    pipeline_steps_from_value,
    skill_output_to_dict,
)
from catalog.skills.repo_skill import SkillRecord, get_skill
from catalog.skills.skill_tools import config_hash
from catalog.storage.repo_session_skill import list_session_skills
from catalog.skills.script_runner import (
    SCRIPT_CODE_CONTRACT_EN,
    ScriptRuntimeError,
    ScriptValidationError,
    prepare_script_input,
    run_skill_script_async,
    validate_script,
)
from catalog.skills.verify import (
    registered_checks,
    run_verify_async,
    validate_verify_checks,
    verify_checks_params_hint,
)
from catalog.storage.db import Database
from catalog.storage.repo_session_artifact import (
    SCRIPT_DRY_RUN_SLOT,
    code_sha256,
    dry_run_slot,
    get_artifact,
    get_script_dry_run,
    list_artifacts,
    upsert_artifact,
    upsert_script_dry_run,
)
from catalog.storage.repo_session import get_sessions_by_skill_id
from catalog.storage.repo_session_document import list_session_documents

NotifyFn = Callable[[], Awaitable[None]]

_PREVIEW_LIMIT = 2000
_PREVIEW_MARK = "…[truncated]"
_TRY_LIMIT_ERROR = "try_skill_script limit exceeded"
_DOC_SCOPE_ERROR = "document_not_available_in_session"


def _preview_text(text: str) -> str:
    if len(text) <= _PREVIEW_LIMIT:
        return text
    return text[:_PREVIEW_LIMIT] + _PREVIEW_MARK


def _result_as_text(value: str | list[str]) -> str:
    if isinstance(value, list):
        if len(value) == 1:
            return value[0]
        return "\n\n---\n\n".join(value)
    return value


def _collection_preview(value: list[str]) -> str:
    return "\n\n---\n\n".join(
        f"[{i + 1}/{len(value)}]\n{item}" for i, item in enumerate(value)
    )


def _draft_outputs(db: Database, session_id: str) -> list[SkillOutput]:
    row = get_artifact(db, session_id, "outputs")
    if row is None or not row.is_valid:
        return []
    parsed, errors = parse_skill_outputs(row.content)
    if errors:
        return []
    return parsed


def sync_draft_outputs_artifact(
    db: Database, skill_id: str, outputs: list[SkillOutput]
) -> None:
    """Keep the session's ``outputs`` artifact in sync with a configure() edit.

    CATALOG-155 / ADR-0015: the settings modal writes outputs straight into
    ``config_json`` via ``update_skill_config``. Build re-packs a skill from
    session artifacts, so without this a later rebuild from the *same*
    session would silently discard the human's edit and restore whatever
    ``set_skill_outputs`` last wrote — reproducing the exact bug this task
    exists to close. Chosen sync strategy is variant (a) from the plan:
    write to both the frozen config *and* the session artifact.

    Only edit sessions (``POST /skills/{id}/edit``, CATALOG-17) carry
    ``session.skill_id``; a draft that was never opened for editing has no
    linked session and nothing to sync — this is a no-op, not an error, so
    configure never fails because of it. A skill can have several live edit
    sessions at once (every ``edit`` call opens a new one, none are ever
    closed), and build can rebuild from any of them — so every linked
    session's artifact is synced, not just the most recently touched one,
    otherwise a build from an older session would silently restore the
    stale ``outputs`` artifact and discard the human's edit (ADR-0015).
    """
    session_rows = get_sessions_by_skill_id(db, skill_id)
    if not session_rows:
        return
    content = json.dumps(
        [skill_output_to_dict(item) for item in outputs], ensure_ascii=False
    )
    for session_row in session_rows:
        upsert_artifact(
            db,
            session_id=session_row.id,
            type="outputs",
            content=content,
            source="user",
            is_valid=True,
            error=None,
        )


def _try_dict_allowed(
    db: Database, session_id: str, step_index: int | None
) -> bool:
    if step_index is None:
        return True
    row = get_artifact(db, session_id, "steps")
    if row is None:
        return True
    parsed, errors = parse_steps_content(row.content)
    if errors or not parsed:
        return True
    return step_index == len(parsed) - 1


def _match_try_outputs(
    outputs: list[SkillOutput], value: dict[str, str | list[str]]
) -> dict[str, str | list[str]]:
    declared_items = {item.key: item for item in outputs}
    declared = list(declared_items)
    if not declared:
        raise ValueError("skill returned a dict but SkillConfig.outputs is empty")
    if len(value) > MAX_SKILL_OUTPUTS:
        raise ValueError(
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
        raise ValueError("; ".join(parts))
    return {key: value[key] for key in declared}


def _try_finalize_output(
    raw: str | list[str] | dict[str, str | list[str]],
    outputs: list[SkillOutput],
    *,
    dict_allowed: bool,
) -> tuple[str, str, str, int | None]:
    if isinstance(raw, dict):
        if not dict_allowed:
            raise ValueError(
                "named outputs are only allowed on the last pipeline step"
            )
        artifacts = _match_try_outputs(outputs, raw)
        primary_item = outputs[0]
        primary_value = artifacts[primary_item.key]
        primary = _result_as_text(primary_value)
        if len(artifacts) == 1:
            if primary_item.multiple and isinstance(primary_value, list):
                return (
                    _collection_preview(primary_value),
                    "collection",
                    primary,
                    len(primary_value),
                )
            return primary, "dict", primary, None
        declared_items = {item.key: item for item in outputs}
        # Every ``multiple`` key gets the same ``[i/N]``-marked rendering as
        # the single-key branch above (``_collection_preview``), not the
        # unmarked ``_result_as_text`` join — otherwise the canonical
        # {index, chapters} shape (a plain key alongside a collection key)
        # silently took a different, marker-less preview format from a
        # sole-collection output.
        preview = "\n\n---\n\n".join(
            f"{key}:\n"
            + (
                _collection_preview(artifacts[key])
                if (item := declared_items.get(key)) is not None
                and item.multiple
                and isinstance(artifacts[key], list)
                else _result_as_text(artifacts[key])
            )
            for key in artifacts
        )
        # A dry-run result can carry a collection alongside companion keys
        # (e.g. split_by_chapters_with_index: {index, chapters[]}) — the
        # planner still needs to see the split before build, so report the
        # total element count across *every* declared collection key
        # (ADR-0025 Decision 5 defines the budget as the sum over all
        # ``multiple`` keys, mirrored by ``_collection_element_count`` /
        # ``persist_run_outputs`` on the enforcement path), not just the first
        # one, or a second
        # collection key's elements silently vanish from the dry-run count.
        collection_lengths = [
            len(artifacts[item.key])
            for item in outputs
            if item.multiple and isinstance(artifacts.get(item.key), list)
        ]
        if collection_lengths:
            return preview, "collection", primary, sum(collection_lengths)
        return preview, "dict", primary, None
    if outputs and dict_allowed:
        raise ValueError("skill declared outputs but script did not return a dict")
    if isinstance(raw, list):
        text = _result_as_text(raw)
        return text, "list", text, None
    return raw, "str", raw, None


def _saved_slot_code(
    db: Database,
    session_id: str,
    *,
    step_index: int | None,
) -> tuple[str | None, str | None]:
    if step_index is not None:
        row = get_artifact(db, session_id, "steps")
        if row is None:
            return None, "steps artifact is missing"
        parsed, errors = parse_steps_content(row.content)
        if errors:
            return None, errors[0]
        if isinstance(step_index, bool) or not isinstance(step_index, int):
            return None, "step_index must be an integer"
        if step_index < 0 or step_index >= len(parsed):
            return None, "step_index out of range"
        step = parsed[step_index]
        if step.type != "script":
            return None, "step is not a script step"
        if not step.code.strip():
            return None, "script code is empty"
        return step.code, None
    row = get_artifact(db, session_id, "script")
    if row is None or not row.content.strip():
        return None, "script code is empty"
    return row.content, None


def _persist_try_dry_run(
    db: Database,
    session_id: str,
    *,
    slot: str,
    step_index: int | None,
    code: str,
    payload: dict[str, Any],
) -> None:
    saved, _error = _saved_slot_code(db, session_id, step_index=step_index)
    if saved is None or code_sha256(saved) != code_sha256(code):
        return
    upsert_script_dry_run(
        db,
        session_id=session_id,
        slot=slot,
        sha256=code_sha256(code),
        ok=bool(payload.get("ok")),
        stage=payload.get("stage"),
        error=payload.get("error"),
    )


def _dry_run_view(
    slot: str,
    code: str,
    stored,
) -> dict[str, Any]:
    digest = code_sha256(code)
    if stored is None:
        return {
            "slot": slot,
            "sha256": digest,
            "ok": False,
            "stage": None,
            "error": None,
            "time": None,
        }
    matches = stored.sha256 == digest
    return {
        "slot": stored.slot,
        "sha256": stored.sha256,
        "ok": bool(stored.ok and matches),
        "stage": stored.stage,
        "error": stored.error,
        "time": stored.time,
    }


def _dry_run_for_artifact(db: Database, row) -> dict[str, Any] | list[dict[str, Any]] | None:
    if row.type == "script":
        stored = get_script_dry_run(db, row.session_id, SCRIPT_DRY_RUN_SLOT)
        return _dry_run_view(SCRIPT_DRY_RUN_SLOT, row.content, stored)
    if row.type == "steps":
        parsed, errors = parse_steps_content(row.content)
        if errors:
            return []
        views: list[dict[str, Any]] = []
        for index, step in enumerate(parsed):
            if step.type != "script":
                continue
            slot = dry_run_slot(index)
            stored = get_script_dry_run(db, row.session_id, slot)
            views.append(_dry_run_view(slot, step.code, stored))
        return views
    return None


def _try_payload(
    *,
    ok: bool,
    stage: str | None = None,
    error: str | None = None,
    input_preview: str = "",
    input_len: int = 0,
    output_preview: str = "",
    output_len: int = 0,
    output_kind: str | None = None,
    # ADR-0025: element count for a collection output (``output_kind ==
    # "collection"``); ``None`` for str/dict/list (a plain ``list`` result
    # with no declared outputs is joined into one document, so it has no
    # separate element count here).
    output_count: int | None = None,
    duration_ms: int = 0,
    verify: dict | None = None,
    line_no: int | None = None,
    source_line: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "stage": stage,
        "error": error,
        "input_preview": input_preview,
        "input_len": input_len,
        "output_preview": output_preview,
        "output_len": output_len,
        "output_kind": output_kind,
        "output_count": output_count,
        "duration_ms": duration_ms,
        "verify": verify,
        "line_no": line_no,
        "source_line": source_line,
    }


def _resolve_try_code(
    db: Database,
    session_id: str,
    *,
    code: str | None,
    step_index: int | None,
) -> tuple[str | None, str | None]:
    if code is not None:
        text = code if isinstance(code, str) else str(code)
        if text.strip():
            return text, None
        return None, "script code is empty"
    return _saved_slot_code(db, session_id, step_index=step_index)


def _resolve_try_documents(
    db: Database,
    session_id: str,
    doc_ids: list[str] | str | None,
) -> tuple[list, str | None]:
    attached = list_session_documents(db, session_id)
    by_id = {row.id: row for row in attached}
    if doc_ids is None:
        return attached, None
    if isinstance(doc_ids, str):
        requested = [doc_ids] if doc_ids.strip() else []
    else:
        requested = [str(item).strip() for item in doc_ids if str(item).strip()]
    resolved = []
    for doc_id in requested:
        row = by_id.get(doc_id)
        if row is None:
            return [], _DOC_SCOPE_ERROR
        resolved.append(row)
    return resolved, None


def _draft_verify_checks(db: Database, session_id: str) -> list[VerifyCheck]:
    meta = get_artifact(db, session_id, "meta")
    if meta is None:
        return []
    try:
        payload = json.loads(meta.content)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    raw = payload.get("verify_checks") or []
    if not isinstance(raw, list):
        return []
    checks: list[VerifyCheck] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("check")
        if not isinstance(name, str) or not name:
            continue
        params = item.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        checks.append(VerifyCheck(check=name, params=dict(params)))
    return checks


async def run_try_skill_script(
    db: Database,
    session_id: str,
    *,
    workspace_dir: str,
    code: str | None = None,
    doc_ids: list[str] | str | None = None,
    step_index: int | None = None,
    budget: SkillBudget | None = None,
) -> dict[str, Any]:
    if not consume_script_try(budget, session_id=session_id):
        return _try_payload(ok=False, error=_TRY_LIMIT_ERROR)
    source, code_error = _resolve_try_code(
        db, session_id, code=code, step_index=step_index
    )
    docs, doc_error = _resolve_try_documents(db, session_id, doc_ids)
    if doc_error is not None:
        return _try_payload(ok=False, error=doc_error)
    doc_texts: list[str] = []
    for row in docs:
        path = str(Path(workspace_dir) / row.path)
        try:
            doc_texts.append(extract_text(path, row.kind))
        except (OSError, ValueError) as exc:
            return _try_payload(ok=False, error=str(exc))
    input_text, _documents = prepare_script_input(doc_texts)
    input_preview = _preview_text(input_text)
    input_len = len(input_text)
    slot = dry_run_slot(step_index)
    if source is None or code_error is not None:
        return _try_payload(
            ok=False,
            stage="validate",
            error=code_error or "script code is empty",
            input_preview=input_preview,
            input_len=input_len,
        )
    try:
        validate_script(source)
    except ScriptValidationError as exc:
        payload = _try_payload(
            ok=False,
            stage="validate",
            error=str(exc),
            input_preview=input_preview,
            input_len=input_len,
        )
        _persist_try_dry_run(
            db,
            session_id,
            slot=slot,
            step_index=step_index,
            code=source,
            payload=payload,
        )
        return payload
    started = time.perf_counter()
    try:
        output = await run_skill_script_async(source, doc_texts)
    except ScriptValidationError as exc:
        payload = _try_payload(
            ok=False,
            stage="validate",
            error=str(exc),
            input_preview=input_preview,
            input_len=input_len,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        _persist_try_dry_run(
            db,
            session_id,
            slot=slot,
            step_index=step_index,
            code=source,
            payload=payload,
        )
        return payload
    except ScriptRuntimeError as exc:
        payload = _try_payload(
            ok=False,
            stage="run",
            error=str(exc),
            input_preview=input_preview,
            input_len=input_len,
            duration_ms=int((time.perf_counter() - started) * 1000),
            line_no=exc.line_no,
            source_line=exc.source_line,
        )
        _persist_try_dry_run(
            db,
            session_id,
            slot=slot,
            step_index=step_index,
            code=source,
            payload=payload,
        )
        return payload
    duration_ms = int((time.perf_counter() - started) * 1000)
    try:
        output_text, output_kind, verify_text, output_count = _try_finalize_output(
            output,
            _draft_outputs(db, session_id),
            dict_allowed=_try_dict_allowed(db, session_id, step_index),
        )
    except ValueError as exc:
        payload = _try_payload(
            ok=False,
            stage="run",
            error=str(exc),
            input_preview=input_preview,
            input_len=input_len,
            duration_ms=duration_ms,
        )
        _persist_try_dry_run(
            db,
            session_id,
            slot=slot,
            step_index=step_index,
            code=source,
            payload=payload,
        )
        return payload
    checks = _draft_verify_checks(db, session_id)
    verify_payload = None
    stage = "run"
    if checks:
        result = await run_verify_async(verify_text, checks, db=db)
        verify_payload = result.as_payload()
        stage = "verify"
    payload = _try_payload(
        ok=True,
        stage=stage,
        input_preview=input_preview,
        input_len=input_len,
        output_preview=_preview_text(output_text),
        output_len=len(output_text),
        output_kind=output_kind,
        output_count=output_count,
        duration_ms=duration_ms,
        verify=verify_payload,
    )
    _persist_try_dry_run(
        db,
        session_id,
        slot=slot,
        step_index=step_index,
        code=source,
        payload=payload,
    )
    return payload


def artifact_payload(db: Database, row) -> dict[str, Any]:
    return {
        "type": row.type,
        "content": row.content,
        "is_valid": row.is_valid,
        "error": row.error,
        "source": row.source,
        "updated_at": row.updated_at,
        "dry_run": _dry_run_for_artifact(db, row),
    }


def artifacts_frame(db: Database, session_id: str) -> dict[str, Any]:
    return {
        "type": "session_artifacts",
        "artifacts": [
            artifact_payload(db, row) for row in list_artifacts(db, session_id)
        ],
    }


def _validate_meta_fields(
    *,
    kind: str,
    allowed_tools: list[str],
    verify_checks: list[dict],
    available_tools: list[str],
    available_checks: list[str],
) -> list[str]:
    errors: list[str] = []
    if kind not in SKILL_KINDS:
        errors.append(f"unknown skill kind: {kind!r}")
        return errors
    if kind == "agent":
        for name in allowed_tools:
            if name not in available_tools:
                errors.append(f"unknown tool: {name!r}")
    errors.extend(
        validate_verify_checks(verify_checks, available_checks=available_checks)
    )
    return errors


def _skill_step_ref_errors(
    step: PipelineStep,
    label: str,
    *,
    session_skills: Mapping[str, SkillRecord] | None,
    lookup_skill: Callable[[str], SkillRecord | None] | None,
) -> list[str]:
    skill_id = step.skill_id.strip()
    if not skill_id:
        return [f"step {label}: skill_id is empty"]
    if step.config is not None or session_skills is None:
        return []
    record = session_skills.get(skill_id)
    if record is None:
        found = lookup_skill(skill_id) if lookup_skill is not None else None
        if found is None:
            return [f"step {label}: skill {skill_id!r} not found"]
        return [f"step {label}: skill {skill_id!r} is not attached to this session"]
    if record.status != "committed":
        return [f"step {label}: skill {skill_id!r} is not committed"]
    if record.config.kind not in SKILL_KINDS:
        return [
            f"step {label}: skill {skill_id!r} has unknown kind {record.config.kind!r}"
        ]
    return []


def validate_pipeline_steps(
    steps: list[PipelineStep],
    available_tools: list[str],
    *,
    require_content: bool = True,
    session_skills: Mapping[str, SkillRecord] | None = None,
    lookup_skill: Callable[[str], SkillRecord | None] | None = None,
) -> list[str]:
    errors: list[str] = []
    if not steps:
        errors.append("pipeline skill must have at least one step")
        return errors
    seen: list[str] = []
    for step in steps:
        label = step.id or "(missing id)"
        if not step.id:
            errors.append("pipeline step id must be non-empty")
        elif step.id in seen:
            errors.append(f"duplicate pipeline step id: {step.id!r}")
        else:
            seen.append(step.id)
        if step.type not in PIPELINE_STEP_TYPES:
            errors.append(f"step {label}: unknown type {step.type!r}")
        if step.input not in PIPELINE_STEP_INPUTS:
            errors.append(f"step {label}: unknown input {step.input!r}")
        if step.type == "script":
            if require_content or step.code.strip():
                try:
                    validate_script(step.code)
                except ScriptValidationError as exc:
                    errors.append(f"step {label}: {exc}")
        elif step.type == "llm":
            if require_content and not step.system_prompt.strip():
                errors.append(f"step {label}: llm prompt is empty")
            for name in step.allowed_tools:
                if name not in available_tools:
                    errors.append(f"step {label}: unknown tool: {name!r}")
        elif step.type == "skill":
            errors.extend(
                _skill_step_ref_errors(
                    step,
                    label,
                    session_skills=session_skills,
                    lookup_skill=lookup_skill,
                )
            )
            if require_content and step.config is None:
                errors.append(f"step {label}: skill snapshot is missing")
    return errors


def resolve_pipeline_skill_steps(
    steps: list[PipelineStep],
    db: Database,
    session_id: str,
) -> tuple[list[PipelineStep], list[str]]:
    attached = {row.id: row for row in list_session_skills(db, session_id)}
    filled: list[PipelineStep] = []
    errors: list[str] = []
    for step in steps:
        if step.type != "skill":
            filled.append(step)
            continue
        label = step.id or "(missing id)"
        record = attached.get(step.skill_id.strip())
        if (
            record is not None
            and record.status == "committed"
            and record.config.kind in SKILL_KINDS
        ):
            snapshot = record.config
            filled.append(
                replace(
                    step,
                    skill_id=record.id,
                    skill_name=record.name,
                    config_hash=config_hash(snapshot.to_json()),
                    config=snapshot,
                )
            )
            continue
        if step.skill_id.strip() and step.config is not None:
            filled.append(step)
            continue
        errors.extend(
            _skill_step_ref_errors(
                step,
                label,
                session_skills=attached,
                lookup_skill=lambda skill_id: get_skill(db, skill_id),
            )
        )
        filled.append(step)
    return filled, errors


def session_skill_lookup(
    db: Database, session_id: str
) -> tuple[dict[str, SkillRecord], Callable[[str], SkillRecord | None]]:
    attached = {row.id: row for row in list_session_skills(db, session_id)}
    return attached, lambda skill_id: get_skill(db, skill_id)


def parse_steps_content(content: str) -> tuple[list[PipelineStep], list[str]]:
    try:
        data = json.loads(content)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return [], [f"steps must be JSON: {exc}"]
    try:
        return pipeline_steps_from_value(data), []
    except (TypeError, ValueError) as exc:
        return [], [str(exc)]


def build_artifact_tools(
    db: Database,
    session_id: str,
    *,
    available_tools: list[str],
    on_artifacts_changed: NotifyFn | None = None,
    workspace_dir: str = "",
    budget: SkillBudget | None = None,
) -> ToolRegistry:
    reg = ToolRegistry()
    available_checks = registered_checks()

    async def _notify() -> None:
        if on_artifacts_changed is not None:
            await on_artifacts_changed()

    async def _save_skill_prompt(*, content: str) -> dict[str, Any]:
        text = content if isinstance(content, str) else str(content)
        is_valid = bool(text.strip())
        error = None if is_valid else "prompt is empty"
        row = upsert_artifact(
            db,
            session_id=session_id,
            type="prompt",
            content=text,
            source="llm",
            is_valid=is_valid,
            error=error,
        )
        await _notify()
        return {"ok": is_valid, "artifact": artifact_payload(db, row)}

    async def _save_skill_script(*, code: str) -> dict[str, Any]:
        text = code if isinstance(code, str) else str(code)
        is_valid = True
        error: str | None = None
        try:
            validate_script(text)
        except ScriptValidationError as exc:
            is_valid = False
            error = str(exc)
        row = upsert_artifact(
            db,
            session_id=session_id,
            type="script",
            content=text,
            source="llm",
            is_valid=is_valid,
            error=error,
        )
        await _notify()
        return {"ok": is_valid, "artifact": artifact_payload(db, row), "error": error}

    async def _set_skill_meta(
        *,
        name: str,
        description: str,
        kind: str,
        input_arity: int | None = None,
        allowed_tools: list[str] | None = None,
        verify_checks: list[dict] | None = None,
    ) -> dict[str, Any]:
        tools = list(allowed_tools or [])
        checks = list(verify_checks or [])
        errors = _validate_meta_fields(
            kind=kind,
            allowed_tools=tools,
            verify_checks=checks,
            available_tools=available_tools,
            available_checks=available_checks,
        )
        name_text = name.strip() if isinstance(name, str) else ""
        if not name_text:
            errors.append("name must be non-empty")
        if not isinstance(description, str):
            errors.append("description must be a string")
            description = ""
        if input_arity is not None and (
            isinstance(input_arity, bool) or input_arity not in (1, 2)
        ):
            errors.append("input_arity must be 1, 2, or null")
            input_arity = None
        payload = {
            "name": name_text,
            "description": description,
            "kind": kind,
            "input_arity": input_arity,
            "allowed_tools": tools if kind == "agent" else [],
            "verify_checks": checks,
        }
        is_valid = not errors
        error = "; ".join(errors) if errors else None
        row = upsert_artifact(
            db,
            session_id=session_id,
            type="meta",
            content=json.dumps(payload, ensure_ascii=False),
            source="llm",
            is_valid=is_valid,
            error=error,
        )
        await _notify()
        return {"ok": is_valid, "artifact": artifact_payload(db, row), "error": error}

    async def _set_skill_outputs(*, outputs: list[dict] | str) -> dict[str, Any]:
        parsed, errors = parse_skill_outputs(outputs)
        is_valid = not errors
        error = "; ".join(errors) if errors else None
        if isinstance(outputs, str):
            content = (
                json.dumps([skill_output_to_dict(item) for item in parsed], ensure_ascii=False)
                if is_valid
                else outputs
            )
        else:
            content = json.dumps(
                [skill_output_to_dict(item) for item in parsed]
                if is_valid
                else outputs,
                ensure_ascii=False,
            )
        row = upsert_artifact(
            db,
            session_id=session_id,
            type="outputs",
            content=content,
            source="llm",
            is_valid=is_valid,
            error=error,
        )
        await _notify()
        return {"ok": is_valid, "artifact": artifact_payload(db, row), "error": error}

    async def _save_skill_steps(*, steps: list[dict] | dict) -> dict[str, Any]:
        errors: list[str] = []
        parsed: list[PipelineStep] = []
        try:
            parsed = pipeline_steps_from_value(steps)
        except (TypeError, ValueError) as exc:
            errors.append(str(exc))
        if not errors:
            attached, lookup = session_skill_lookup(db, session_id)
            errors.extend(
                validate_pipeline_steps(
                    parsed,
                    available_tools,
                    require_content=False,
                    session_skills=attached,
                    lookup_skill=lookup,
                )
            )
        payload = {"steps": [pipeline_step_to_dict(s) for s in parsed]}
        is_valid = not errors
        error = "; ".join(errors) if errors else None
        row = upsert_artifact(
            db,
            session_id=session_id,
            type="steps",
            content=json.dumps(payload, ensure_ascii=False),
            source="llm",
            is_valid=is_valid,
            error=error,
        )
        await _notify()
        return {"ok": is_valid, "artifact": artifact_payload(db, row), "error": error}

    async def _list_session_skills() -> dict[str, Any]:
        rows = [
            row
            for row in list_session_skills(db, session_id)
            if row.status == "committed"
        ]
        return {
            "skills": [
                {
                    "id": row.id,
                    "name": row.name,
                    "kind": row.config.kind,
                    "status": row.status,
                    "description": row.description or "",
                }
                for row in rows
            ]
        }

    async def _read_skill_draft() -> dict[str, Any]:
        rows = list_artifacts(db, session_id)
        out: dict[str, Any] = {
            "artifacts": [artifact_payload(db, r) for r in rows],
        }
        meta = get_artifact(db, session_id, "meta")
        if meta is not None:
            try:
                out["meta"] = json.loads(meta.content)
            except (TypeError, ValueError, json.JSONDecodeError):
                out["meta"] = None
        outputs_row = get_artifact(db, session_id, "outputs")
        if outputs_row is not None:
            parsed, errors = parse_skill_outputs(outputs_row.content)
            out["outputs"] = (
                [skill_output_to_dict(item) for item in parsed] if not errors else None
            )
        return out

    async def _try_skill_script(
        *,
        code: str | None = None,
        doc_ids: list[str] | str | None = None,
        step_index: int | None = None,
    ) -> dict[str, Any]:
        result = await run_try_skill_script(
            db,
            session_id,
            workspace_dir=workspace_dir,
            code=code,
            doc_ids=doc_ids,
            step_index=step_index,
            budget=budget,
        )
        await _notify()
        return result

    reg.register(
        ToolSpec(
            name="save_skill_prompt",
            description=(
                "Save the agent skill system_prompt draft for this session. "
                "Call when the prompt is ready or updated; do not paste the "
                "full prompt into chat."
            ),
            parameters={
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
            },
        ),
        _save_skill_prompt,
    )
    reg.register(
        ToolSpec(
            name="save_skill_script",
            description=(
                "Save the deterministic Python script draft for this session. "
                + SCRIPT_CODE_CONTRACT_EN
                + ". Then call try_skill_script and fix until ok before "
                "building. On validation error, fix the code and call again."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": (
                            "Python source. " + SCRIPT_CODE_CONTRACT_EN + "."
                        ),
                    }
                },
                "required": ["code"],
            },
        ),
        _save_skill_script,
    )
    reg.register(
        ToolSpec(
            name="set_skill_meta",
            description=(
                "Set skill metadata for this session: name, description, kind "
                "(agent|script|pipeline), optional input_arity, allowed_tools, "
                "verify_checks. For pipeline, allowed_tools belong on steps, "
                "not here. Call when kind/name are clear. "
                + verify_checks_params_hint()
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": ["agent", "script", "pipeline"],
                    },
                    "input_arity": {"type": ["integer", "null"]},
                    "allowed_tools": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "verify_checks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "check": {
                                    "type": "string",
                                    "enum": available_checks,
                                },
                                "params": {"type": "object"},
                            },
                            "required": ["check"],
                        },
                    },
                },
                "required": ["name", "description", "kind"],
            },
        ),
        _set_skill_meta,
    )
    reg.register(
        ToolSpec(
            name="set_skill_outputs",
            description=(
                "Declare named skill outputs for this session as "
                "[{key, description, multiple?}, ...]. First item is primary. "
                "Keys must match ^[a-z][a-z0-9_]{0,31}$, be unique, "
                "and descriptions must be non-empty. At most 8 items. "
                "Omit or use [] for a single unnamed output. For script "
                "skills the return dict must use these keys. "
                "multiple:true marks a key as a collection whose element "
                "count depends on the input (e.g. one per chapter): script "
                "returns list[str] for that key, agent calls emit_output "
                "once per element (calls accumulate into a list). Use "
                "multiple for 'how many depends on the input', not for "
                "distinct roles (e.g. text + table) — those are separate "
                "non-multiple keys."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "outputs": {
                        "type": "array",
                        "maxItems": 8,
                        "items": {
                            "type": "object",
                            "properties": {
                                "key": {
                                    "type": "string",
                                    "pattern": r"^[a-z][a-z0-9_]{0,31}$",
                                },
                                "description": {"type": "string"},
                                "multiple": {
                                    "type": "boolean",
                                    "description": (
                                        "True if this key persists as N "
                                        "documents (element count unknown "
                                        "until run time)."
                                    ),
                                },
                            },
                            "required": ["key", "description"],
                        },
                    }
                },
                "required": ["outputs"],
            },
        ),
        _set_skill_outputs,
    )
    reg.register(
        ToolSpec(
            name="save_skill_steps",
            description=(
                "Save the pipeline steps draft for this session. Each step "
                "has id, type (script|llm|skill), input (documents|previous). "
                "script steps need code; llm steps need system_prompt, "
                "optional model/provider/reasoning/allowed_tools; skill steps "
                "need skill_id of a committed skill attached to this session. "
                "Call after set_skill_meta(kind=pipeline)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "type": {
                                    "type": "string",
                                    "enum": list(PIPELINE_STEP_TYPES),
                                },
                                "input": {
                                    "type": "string",
                                    "enum": ["documents", "previous"],
                                },
                                "code": {"type": "string"},
                                "system_prompt": {"type": "string"},
                                "prompt": {"type": "string"},
                                "allowed_tools": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "model": {"type": "string"},
                                "provider": {"type": "string"},
                                "reasoning": {"type": "string"},
                                "skill_id": {"type": "string"},
                            },
                            "required": ["id", "type"],
                        },
                    }
                },
                "required": ["steps"],
            },
        ),
        _save_skill_steps,
    )
    reg.register(
        ToolSpec(
            name="list_session_skills",
            description=(
                "List committed skills attached to this session. Use the id "
                "as skill_id on a pipeline step with type=skill."
            ),
            parameters={"type": "object", "properties": {}},
        ),
        _list_session_skills,
    )
    reg.register(
        ToolSpec(
            name="read_skill_draft",
            description=(
                "Read the current session skill draft artifacts (prompt, "
                "script, meta, steps, outputs) including script dry_run status."
            ),
            parameters={"type": "object", "properties": {}},
        ),
        _read_skill_draft,
    )
    reg.register(
        ToolSpec(
            name="try_skill_script",
            description=(
                "Dry-run the session script draft in the same sandbox as apply. "
                "Call after save_skill_script and fix the code until ok before "
                "building. input_preview is the actual script input (markdown "
                "tables from docx/xlsx) — parse that, do not guess. Does not "
                "save documents or skill_run. Optional code overrides the "
                "script artifact; optional doc_ids must belong to this "
                "session; optional step_index runs a pipeline script step."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "doc_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "step_index": {"type": "integer"},
                },
            },
        ),
        _try_skill_script,
    )
    return reg
