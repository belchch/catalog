from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from catalog.agent.registry import ToolRegistry
from catalog.llm.base import ToolSpec
from catalog.skills.config import (
    PIPELINE_STEP_INPUTS,
    PIPELINE_STEP_TYPES,
    SKILL_KINDS,
    PipelineStep,
    pipeline_step_to_dict,
    pipeline_steps_from_value,
)
from catalog.skills.script_runner import (
    SCRIPT_CODE_CONTRACT_EN,
    ScriptValidationError,
    validate_script,
)
from catalog.skills.verify import registered_checks
from catalog.storage.db import Database
from catalog.storage.repo_session_artifact import (
    get_artifact,
    list_artifacts,
    upsert_artifact,
)

NotifyFn = Callable[[], Awaitable[None]]


def _artifact_payload(row) -> dict[str, Any]:
    return {
        "type": row.type,
        "content": row.content,
        "is_valid": row.is_valid,
        "error": row.error,
        "source": row.source,
        "updated_at": row.updated_at,
    }


def artifacts_frame(db: Database, session_id: str) -> dict[str, Any]:
    return {
        "type": "session_artifacts",
        "artifacts": [
            _artifact_payload(row) for row in list_artifacts(db, session_id)
        ],
    }


VERIFY_CHECK_PARAMS_HINT = (
    "verify_checks params: non_empty/markdown_well_formed/"
    "no_leftover_placeholders (no params); "
    "min_length requires params.min (unit chars|lines); "
    "max_length requires params.max (unit chars|lines); "
    "regex_matches requires params.pattern; "
    "has_section requires params.heading (optional level); "
    "has_field requires params.key; "
    "table_parses optional params.min_rows/min_cols."
)


def validate_verify_check_entry(
    vc: object, available_checks: list[str]
) -> list[str]:
    errors: list[str] = []
    if not isinstance(vc, dict):
        errors.append("verify check must be an object")
        return errors
    check_id = vc.get("check")
    if isinstance(check_id, str) and (
        check_id == "custom" or check_id.startswith("custom:")
    ):
        if check_id == "custom":
            params = vc.get("params") or {}
            if not isinstance(params, dict) or not params.get("id"):
                errors.append("custom check requires params.id")
        elif check_id == "custom:" or len(check_id) <= len("custom:"):
            errors.append("custom check id is empty")
        return errors
    if not check_id or check_id not in available_checks:
        errors.append(f"unknown verify check: {check_id!r}")
        return errors
    params = vc.get("params") or {}
    if not isinstance(params, dict):
        errors.append(f"{check_id}: params must be an object")
        return errors
    if check_id == "min_length" and params.get("min") is None:
        errors.append("min_length requires params.min")
    if check_id == "max_length" and params.get("max") is None:
        errors.append("max_length requires params.max")
    if check_id == "regex_matches" and not params.get("pattern"):
        errors.append("regex_matches requires params.pattern")
    if check_id == "has_section" and not params.get("heading"):
        errors.append("has_section requires params.heading")
    if check_id == "has_field" and not params.get("key"):
        errors.append("has_field requires params.key")
    return errors


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
    for vc in verify_checks:
        errors.extend(validate_verify_check_entry(vc, available_checks))
    return errors


def validate_pipeline_steps(
    steps: list[PipelineStep],
    available_tools: list[str],
    *,
    require_content: bool = True,
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
    return errors


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
        return {"ok": is_valid, "artifact": _artifact_payload(row)}

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
        return {"ok": is_valid, "artifact": _artifact_payload(row), "error": error}

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
        return {"ok": is_valid, "artifact": _artifact_payload(row), "error": error}

    async def _save_skill_steps(*, steps: list[dict] | dict) -> dict[str, Any]:
        errors: list[str] = []
        parsed: list[PipelineStep] = []
        try:
            parsed = pipeline_steps_from_value(steps)
        except (TypeError, ValueError) as exc:
            errors.append(str(exc))
        if not errors:
            errors.extend(
                validate_pipeline_steps(
                    parsed, available_tools, require_content=False
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
        return {"ok": is_valid, "artifact": _artifact_payload(row), "error": error}

    async def _read_skill_draft() -> dict[str, Any]:
        rows = list_artifacts(db, session_id)
        out: dict[str, Any] = {
            "artifacts": [_artifact_payload(r) for r in rows],
        }
        meta = get_artifact(db, session_id, "meta")
        if meta is not None:
            try:
                out["meta"] = json.loads(meta.content)
            except (TypeError, ValueError, json.JSONDecodeError):
                out["meta"] = None
        return out

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
                + ". On validation error, fix the code and call again."
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
                + VERIFY_CHECK_PARAMS_HINT
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
                                    "enum": list(available_checks),
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
            name="save_skill_steps",
            description=(
                "Save the pipeline steps draft for this session. Each step "
                "has id, type (script|llm), input (documents|previous). "
                "script steps need code; llm steps need system_prompt, "
                "optional model/provider/reasoning/allowed_tools. "
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
                                    "enum": ["script", "llm"],
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
            name="read_skill_draft",
            description=(
                "Read the current session skill draft artifacts (prompt, "
                "script, meta, steps)."
            ),
            parameters={"type": "object", "properties": {}},
        ),
        _read_skill_draft,
    )
    return reg
