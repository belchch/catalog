"""``POST /sessions/{id}/skills`` (build), ``POST /sessions/{id}/skill-tracks``,
``POST /skills/{id}/commit``, ``POST /skills/{id}/edit``, ``GET /skills``.

CATALOG-53: ``build_skill_from_session`` packs ``session_artifact`` rows into
a :class:`SkillConfig` without an LLM call when artifacts exist. Sessions with
no artifacts keep the legacy LLM ``build_skill`` path as a fallback.

CATALOG-27: phase A proposes operation tracks via ``propose_skill_tracks``;
selecting a track appends a quiet user intent message. When that intent is
present, build skips pure artifact-pack and uses the LLM path so the chosen
operation is respected. Edit sessions (``session.skill_id``) skip phase A.

CATALOG-17: when the build's session was started via ``POST
/skills/{id}/edit`` (``session.skill_id`` set), the same skill is updated in
place (``update_skill``) instead of a new one being created — a committed
skill drops back to ``draft``.
"""

from __future__ import annotations

import json
from dataclasses import replace

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from catalog.api.deps import get_workspace_db, get_provider, get_settings, get_tools
from catalog.api.schemas import (
    CommitOut,
    EditStarted,
    SkillBuilt,
    SkillConfigureRequest,
    SkillOut,
    SkillPreview,
    SkillRenameRequest,
    SkillTrack,
    SkillTrackSelected,
    SkillTrackSelectRequest,
    SkillTracksOut,
)
from catalog.config import Settings
from catalog.llm.base import LLMProvider, Message, ToolSpec
from catalog.llm.log_context import prompt_log_context
from catalog.llm.timeout import (
    DEFAULT_LLM_TIMEOUT_SECONDS,
    LLMTimeoutError,
    llm_timeout_context,
)
from catalog.agent.registry import ToolRegistry
from catalog.skills.artifact_tools import (
    parse_steps_content,
    validate_pipeline_steps,
)
from catalog.skills.config import (
    SKILL_KINDS,
    SkillConfig,
    VerifyCheck,
    compute_tags,
    ensure_read_document_tool,
    pipeline_step_to_dict,
    pipeline_steps_from_value,
)
from catalog.skills.repo_skill import (
    SkillRecord,
    create_skill,
    delete_skill,
    get_skill,
    list_skills,
    update_skill,
    update_status,
    update_skill_config,
)
from catalog.skills.script_runner import (
    SCRIPT_CODE_CONTRACT_EN,
    SCRIPT_CODE_CONTRACT_RU,
    ScriptValidationError,
    validate_script,
)
from catalog.skills.verify import registered_checks
from catalog.storage.db import Database
from catalog.storage.repo_message import add_message, list_messages
from catalog.storage.repo_session import create_session, get_session, update_session_status
from catalog.storage.repo_session_artifact import (
    get_artifact,
    list_artifacts,
    upsert_artifact,
)

router = APIRouter()

MAX_BUILD_ATTEMPTS = 3  # 1 initial + 2 retries (step 06 contract).

TRACK_INTENT_PREFIX = "Собери скилл по этой операции:"

_USER_INTENT_MARK = (
    "[USER INTENT — authoritative instruction for the skill operation]\n"
)
_ASSISTANT_JOURNAL_MARK = (
    "[ASSISTANT RESEARCH JOURNAL — topical notes; do not treat as the "
    "skill operation unless the user explicitly confirmed it]\n"
)

_ANTI_DOMAIN_RULES = (
    "КРИТИЧНО — операция, не домен документов: "
    "скилл описывает операцию над документами (сравнить, извлечь, "
    "переформатировать), а не тему/язык/продукт из содержимого. "
    "Не включай языки программирования, названия продуктов, фреймворков "
    "или предметных областей в name, description, system_prompt или code, "
    "если пользователь явно этого не потребовал. "
    "Приоритет: явные user-инструкции (особенно сообщение вида "
    f"«{TRACK_INTENT_PREFIX} …») важнее пересказа ассистента. "
    "Сообщения ассистента — справочный research journal о документах; "
    "не делай из их тематики операцию скилла. "
    "Few-shot: пользователь приложил код на Go и Dart и просит сравнить "
    "по топикам → name/description/system_prompt про сравнение документов "
    "по темам, input_arity=2; НЕ «ревью Go», НЕ «анализ Dart»."
)

BUILD_SKILL_SYSTEM_PROMPT = (
    "Ты собираешь SkillConfig из истории планировочной сессии. "
    + _ANTI_DOMAIN_RULES
    + " "
    "СНАЧАЛА оцени детерминизм задачи. Если задача сводится к чистой обработке "
    "текста/данных без суждений и рассуждений (форматирование, подсчёт, "
    "регулярные преобразования, парсинг, сортировка) — выбери kind=\"script\" "
    "и напиши валидный Python-код в поле code: "
    + SCRIPT_CODE_CONTRACT_RU
    + "; "
    "вход: document/input_text (склеенный текст) и documents (list[str] по "
    "каждому входу); результат — return из main()/main(document)/main(documents), "
    "глобальная result или print. Если задача требует суждений, "
    "рассуждений или творческой обработки — выбери kind=\"agent\" и ОБЯЗАТЕЛЬНО "
    "заполни non_determinism_reason объяснением, почему детерминизм невозможен. "
    "Для agent также заполни system_prompt (полная инструкция агенту), "
    "allowed_tools (только из доступных инструментов), model, verify_checks "
    "(только из реестра проверок). Укажи input_arity — сколько входных "
    "документов ожидает скил (1, 2, …), либо опусти/null если число любое."
)

PROPOSE_SKILL_TRACKS_SYSTEM_PROMPT = (
    "Ты предлагаешь 1–3 трека операции для сборки скилла из истории "
    "планировочной сессии. "
    + _ANTI_DOMAIN_RULES
    + " "
    "Каждый трек: name (краткое имя операции), description (что делает скилл), "
    "operation (чёткая формулировка операции над документами), input_arity "
    "(сколько входов: 1, 2 или null если любое), rationale (почему этот "
    "трек уместен). Несколько треков — только если намерение пользователя "
    "неоднозначно; при однозначности верни ровно один трек. "
    "Обязательно вызови инструмент propose_skill_tracks."
)

_PROPOSE_SKILL_TRACKS_PARAMETERS = {
    "type": "object",
    "properties": {
        "tracks": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "operation": {"type": "string"},
                    "input_arity": {
                        "type": ["integer", "null"],
                        "description": (
                            "How many input documents: 1, 2, or null for any."
                        ),
                    },
                    "rationale": {"type": "string"},
                },
                "required": [
                    "name",
                    "description",
                    "operation",
                    "rationale",
                ],
            },
        }
    },
    "required": ["tracks"],
}

PROPOSE_SKILL_TRACKS_TOOL = ToolSpec(
    name="propose_skill_tracks",
    description=(
        "Propose 1–3 skill operation tracks for the user to choose from "
        "before building a skill."
    ),
    parameters=_PROPOSE_SKILL_TRACKS_PARAMETERS,
)

# JSON-Schema for the build_skill tool arguments, mirroring SkillConfig fields.
_BUILD_SKILL_PARAMETERS = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "kind": {
            "type": "string",
            "enum": ["agent", "script"],
            "description": (
                "agent = LLM-driven function-calling loop; "
                "script = deterministic pure-Python (no LLM at runtime)."
            ),
        },
        "code": {
            "type": "string",
            "description": (
                "Python source for kind=script skills. "
                + SCRIPT_CODE_CONTRACT_EN
                + "; input via `document`/`documents`; output via "
                "main()/main(document)/main(documents)/result/print."
            ),
        },
        "input_arity": {
            "type": ["integer", "null"],
            "description": (
                "How many input documents this skill expects (CATALOG-4): "
                "1, 2, ... or null for an arbitrary-length list. Omit/null = any >=1."
            ),
        },
        "non_determinism_reason": {
            "type": "string",
            "description": (
                "Required when kind=agent: explain why the task is not "
                "deterministic (needs judgment/reasoning)."
            ),
        },
        "system_prompt": {"type": "string"},
        "allowed_tools": {"type": "array", "items": {"type": "string"}},
        "model": {"type": "string"},
        "temperature": {"type": "number"},
        "max_iterations": {"type": "integer"},
        "max_retries": {"type": "integer"},
        "verify_checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "check": {"type": "string"},
                    "params": {"type": "object"},
                },
                "required": ["check"],
            },
        },
        "output_kind": {"type": "string"},
    },
    "required": ["name", "description", "kind"],
}

BUILD_SKILL_TOOL = ToolSpec(
    name="build_skill",
    description="Build a skill configuration (SkillConfig) from the session history.",
    parameters=_BUILD_SKILL_PARAMETERS,
)


def _annotate_role_content(role: str, content: str) -> str:
    if role == "user":
        return _USER_INTENT_MARK + content
    if role == "assistant":
        return _ASSISTANT_JOURNAL_MARK + content
    return content


def _session_history_messages(messages_raw: list[dict]) -> list[Message]:
    history: list[Message] = []
    for m in messages_raw:
        if m["role"] in ("user", "assistant") and m["content"] is not None:
            history.append(
                Message(
                    role=m["role"],
                    content=_annotate_role_content(m["role"], m["content"]),
                )
            )
    return history


def _has_track_intent(messages_raw: list[dict]) -> bool:
    for m in messages_raw:
        if (
            m["role"] == "user"
            and isinstance(m["content"], str)
            and m["content"].startswith(TRACK_INTENT_PREFIX)
        ):
            return True
    return False


def _format_track_intent_message(track: SkillTrack) -> str:
    arity = (
        str(track.input_arity) if track.input_arity is not None else "любое"
    )
    return (
        f"{TRACK_INTENT_PREFIX} {track.operation}\n"
        f"Название: {track.name}\n"
        f"Описание: {track.description}\n"
        f"input_arity: {arity}\n"
        f"Обоснование: {track.rationale}"
    )


def _parse_tracks_from_args(args: dict) -> list[SkillTrack] | None:
    raw_tracks = args.get("tracks")
    if not isinstance(raw_tracks, list) or not (1 <= len(raw_tracks) <= 3):
        return None
    try:
        return [SkillTrack.model_validate(item) for item in raw_tracks]
    except (ValidationError, TypeError, ValueError):
        return None


def _args_to_config(args: dict, default_model: str) -> SkillConfig:
    """Parse ``build_skill`` tool arguments into a :class:`SkillConfig`.

    For ``kind="script"`` the skill is deterministic: ``allowed_tools`` is
    forced to ``[]`` (no agent loop, no tools) and ``model`` is irrelevant
    (though still stored for uniformity). For ``kind="agent"`` the classic
    frozen-agent fields are populated as before.
    """
    kind = args.get("kind", "agent")
    verify_checks = [
        VerifyCheck(
            check=vc["check"],
            params=dict(vc.get("params", {})),
        )
        for vc in (args.get("verify_checks") or [])
    ]
    if kind in ("script", "pipeline"):
        allowed_tools: list[str] = []
    else:
        allowed_tools = ensure_read_document_tool(
            list(args.get("allowed_tools") or [])
        )
    return SkillConfig(
        name=args["name"],
        description=args["description"],
        system_prompt=args.get("system_prompt") or "",
        allowed_tools=allowed_tools,
        model=args.get("model") or default_model,
        temperature=float(args.get("temperature", 0.0)),
        max_iterations=int(args.get("max_iterations", 8)),
        max_retries=int(args.get("max_retries", 2)),
        verify_checks=verify_checks,
        output_kind=args.get("output_kind", "md"),
        kind=kind,
        code=args.get("code") or "",
        non_determinism_reason=args.get("non_determinism_reason") or "",
        input_arity=args.get("input_arity"),
        provider=args.get("provider") or "",
        reasoning=args.get("reasoning") or "",
        steps=pipeline_steps_from_value(args.get("steps")),
    )


def _validate_config(
    config: SkillConfig, available_tools: list[str], available_checks: list[str]
) -> list[str]:
    """Return a list of validation errors (empty when the config is valid).

    For ``kind="script"`` the code is statically validated via
    :func:`validate_script` (syntax + sandbox policy); ``allowed_tools`` is
    ignored (always empty). For ``kind="agent"`` the classic tool/check
    checks apply. Verify-check ids are validated for both kinds.
    """
    errors: list[str] = []
    if config.kind not in SKILL_KINDS:
        errors.append(
            f"unknown skill kind: {config.kind!r} (expected 'agent', 'script', or 'pipeline')"
        )
        return errors
    if config.kind == "script":
        try:
            validate_script(config.code)
        except ScriptValidationError as exc:
            errors.append(str(exc))
    elif config.kind == "pipeline":
        errors.extend(validate_pipeline_steps(config.steps, available_tools))
    else:
        for name in config.allowed_tools:
            if name not in available_tools:
                errors.append(f"unknown tool: {name!r}")
    # Verify-check ids are validated for both kinds (a script may have checks).
    for vc in config.verify_checks:
        if vc.check not in available_checks:
            errors.append(f"unknown verify check: {vc.check!r}")
    return errors


def _persist_built_skill(
    db: Database, session_id: str, config: SkillConfig
) -> str:
    session_row = get_session(db, session_id)
    edit_target = session_row.skill_id if session_row is not None else None
    if edit_target is not None:
        existing = get_skill(db, edit_target)
        if existing is None:
            raise HTTPException(status_code=404, detail="edited skill not found")
        status_override = "draft" if existing.status == "committed" else None
        update_skill(
            db,
            edit_target,
            name=config.name,
            description=config.description,
            config=config,
            status=status_override,
        )
        skill_id = edit_target
    else:
        skill_id = create_skill(
            db,
            name=config.name,
            description=config.description,
            config=config,
            status="draft",
        )
    update_session_status(db, session_id, "done")
    return skill_id


def _build_skill_from_artifacts(
    *,
    db: Database,
    base_tools: ToolRegistry,
    session_id: str,
    model_default: str,
) -> str | None:
    artifacts = list_artifacts(db, session_id)
    if not artifacts:
        return None

    meta_row = get_artifact(db, session_id, "meta")
    if meta_row is None:
        raise HTTPException(
            status_code=422,
            detail="skill meta is missing; set name/description/kind via set_skill_meta",
        )
    if not meta_row.is_valid:
        raise HTTPException(
            status_code=422,
            detail=f"skill meta is invalid: {meta_row.error or 'unknown error'}",
        )
    try:
        meta = json.loads(meta_row.content)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=422, detail=f"skill meta is not valid JSON: {exc}"
        ) from exc
    if not isinstance(meta, dict):
        raise HTTPException(status_code=422, detail="skill meta must be a JSON object")

    kind = meta.get("kind", "agent")
    args = dict(meta)
    if kind == "script":
        script = get_artifact(db, session_id, "script")
        if script is None or not script.content.strip():
            raise HTTPException(
                status_code=422,
                detail="script artifact is empty; save a script before building",
            )
        if not script.is_valid:
            raise HTTPException(
                status_code=422,
                detail=f"script is invalid: {script.error or 'validation failed'}",
            )
        args["code"] = script.content
        args["system_prompt"] = ""
    elif kind == "pipeline":
        steps_row = get_artifact(db, session_id, "steps")
        if steps_row is None:
            raise HTTPException(
                status_code=422,
                detail="steps artifact is missing; save steps before building",
            )
        if not steps_row.is_valid:
            raise HTTPException(
                status_code=422,
                detail=f"steps are invalid: {steps_row.error or 'validation failed'}",
            )
        parsed, parse_errors = parse_steps_content(steps_row.content)
        if parse_errors:
            raise HTTPException(
                status_code=422,
                detail="steps artifact is invalid: " + "; ".join(parse_errors),
            )
        script = get_artifact(db, session_id, "script")
        prompt = get_artifact(db, session_id, "prompt")
        filled = []
        script_used = False
        prompt_used = False
        for step in parsed:
            if (
                step.type == "script"
                and not step.code.strip()
                and script is not None
                and not script_used
            ):
                if not script.is_valid:
                    raise HTTPException(
                        status_code=422,
                        detail=f"script is invalid: {script.error or 'validation failed'}",
                    )
                step = replace(step, code=script.content)
                script_used = True
            if (
                step.type == "llm"
                and not step.system_prompt.strip()
                and prompt is not None
                and not prompt_used
            ):
                if not prompt.is_valid:
                    raise HTTPException(
                        status_code=422,
                        detail=f"prompt is invalid: {prompt.error or 'validation failed'}",
                    )
                step = replace(step, system_prompt=prompt.content)
                prompt_used = True
            filled.append(step)
        args["steps"] = [pipeline_step_to_dict(s) for s in filled]
        args["code"] = ""
        args["system_prompt"] = ""
        args["allowed_tools"] = []
    else:
        prompt = get_artifact(db, session_id, "prompt")
        if prompt is None or not prompt.content.strip():
            raise HTTPException(
                status_code=422,
                detail="prompt artifact is empty; save a prompt before building",
            )
        if not prompt.is_valid:
            raise HTTPException(
                status_code=422,
                detail=f"prompt is invalid: {prompt.error or 'validation failed'}",
            )
        args["system_prompt"] = prompt.content
        args["code"] = ""

    try:
        config = _args_to_config(args, model_default)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422, detail=f"failed to assemble skill config: {exc}"
        ) from exc

    errors = _validate_config(config, base_tools.names(), registered_checks())
    if errors:
        raise HTTPException(
            status_code=422,
            detail="skill artifacts are invalid: " + "; ".join(errors),
        )
    return _persist_built_skill(db, session_id, config)


async def _build_skill_from_session_llm(
    *,
    provider: LLMProvider,
    db: Database,
    base_tools: ToolRegistry,
    session_id: str,
    model_default: str,
) -> str:
    messages_raw = list_messages(db, session_id)
    history: list[Message] = [
        Message(role="system", content=BUILD_SKILL_SYSTEM_PROMPT),
        *_session_history_messages(messages_raw),
    ]

    available_tools = base_tools.names()
    available_checks = registered_checks()

    with prompt_log_context(session_id=session_id, run_id=None, purpose="build_skill"):
        for _attempt in range(MAX_BUILD_ATTEMPTS):
            resp = await provider.complete(
                model_default,
                history,
                [BUILD_SKILL_TOOL],
                0.0,
            )
            history.append(
                Message(role="assistant", content=resp.content, tool_calls=resp.tool_calls)
            )

            tc = next((t for t in resp.tool_calls if t.name == "build_skill"), None)
            if tc is None:
                history.append(
                    Message(
                        role="user",
                        content="Ты должен вызвать инструмент build_skill. Повтори.",
                    )
                )
                continue

            try:
                config = _args_to_config(tc.arguments, model_default)
            except (KeyError, TypeError, ValueError) as exc:
                history.append(
                    Message(
                        role="user",
                        content=f"Не удалось разобрать конфиг: {exc}. Вызови build_skill заново.",
                    )
                )
                continue

            errors = _validate_config(config, available_tools, available_checks)
            if errors:
                history.append(
                    Message(
                        role="user",
                        content="Конфиг невалиден: "
                        + "; ".join(errors)
                        + ". Исправь и вызови build_skill заново.",
                    )
                )
                continue

            return _persist_built_skill(db, session_id, config)

    raise HTTPException(
        status_code=422,
        detail=(
            "failed to build a valid skill after retries; "
            "the model did not produce a valid SkillConfig. "
            "Refine the plan or retry; if calls are slow, increase the "
            "session LLM timeout and try again."
        ),
    )


async def propose_skill_tracks_from_session(
    *,
    provider: LLMProvider,
    db: Database,
    session_id: str,
    model_default: str,
) -> list[SkillTrack] | None:
    messages_raw = list_messages(db, session_id)
    history: list[Message] = [
        Message(role="system", content=PROPOSE_SKILL_TRACKS_SYSTEM_PROMPT),
        *_session_history_messages(messages_raw),
    ]

    with prompt_log_context(
        session_id=session_id, run_id=None, purpose="propose_skill_tracks"
    ):
        for _attempt in range(MAX_BUILD_ATTEMPTS):
            resp = await provider.complete(
                model_default,
                history,
                [PROPOSE_SKILL_TRACKS_TOOL],
                0.0,
            )
            history.append(
                Message(
                    role="assistant",
                    content=resp.content,
                    tool_calls=resp.tool_calls,
                )
            )

            tc = next(
                (t for t in resp.tool_calls if t.name == "propose_skill_tracks"),
                None,
            )
            if tc is None:
                history.append(
                    Message(
                        role="user",
                        content=(
                            "Ты должен вызвать инструмент propose_skill_tracks. "
                            "Повтори."
                        ),
                    )
                )
                continue

            tracks = _parse_tracks_from_args(tc.arguments)
            if tracks is None:
                history.append(
                    Message(
                        role="user",
                        content=(
                            "Ответ невалиден: нужен массив tracks длины 1–3 "
                            "с полями name, description, operation, rationale "
                            "и опциональным input_arity. Вызови "
                            "propose_skill_tracks заново."
                        ),
                    )
                )
                continue

            return tracks

    return None


def _build_timeout_detail(exc: LLMTimeoutError, timeout_seconds: int) -> str:
    seconds = (
        int(exc.timeout_seconds)
        if exc.timeout_seconds is not None
        else timeout_seconds
    )
    return (
        f"skill build timed out after {seconds}s. "
        "Increase the session LLM timeout (30–300s) and retry."
    )


async def build_skill_from_session(
    *,
    provider: LLMProvider,
    db: Database,
    base_tools: ToolRegistry,
    settings: Settings,
    session_id: str,
    default_model: str | None = None,
) -> str:
    model_default = default_model or settings.default_model
    messages_raw = list_messages(db, session_id)
    force_llm = _has_track_intent(messages_raw)
    if not force_llm:
        packed = _build_skill_from_artifacts(
            db=db,
            base_tools=base_tools,
            session_id=session_id,
            model_default=model_default,
        )
        if packed is not None:
            return packed
    session_row = get_session(db, session_id)
    timeout = (
        session_row.llm_timeout_seconds
        if session_row is not None
        else DEFAULT_LLM_TIMEOUT_SECONDS
    )
    try:
        with llm_timeout_context(float(timeout)):
            return await _build_skill_from_session_llm(
                provider=provider,
                db=db,
                base_tools=base_tools,
                session_id=session_id,
                model_default=model_default,
            )
    except LLMTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=_build_timeout_detail(exc, timeout),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"skill build failed: {exc}",
        ) from exc


def seed_session_artifacts_from_skill(
    db: Database, session_id: str, record: SkillRecord
) -> None:
    config = record.config
    meta = {
        "name": config.name,
        "description": config.description,
        "kind": config.kind,
        "input_arity": config.input_arity,
        "allowed_tools": list(config.allowed_tools),
        "verify_checks": [
            {"check": vc.check, "params": dict(vc.params)}
            for vc in config.verify_checks
        ],
    }
    upsert_artifact(
        db,
        session_id=session_id,
        type="meta",
        content=json.dumps(meta, ensure_ascii=False),
        source="user",
        is_valid=True,
        error=None,
    )
    if config.kind == "pipeline" or config.steps:
        upsert_artifact(
            db,
            session_id=session_id,
            type="steps",
            content=json.dumps(
                {"steps": [pipeline_step_to_dict(s) for s in config.steps]},
                ensure_ascii=False,
            ),
            source="user",
            is_valid=True,
            error=None,
        )
    if config.system_prompt:
        upsert_artifact(
            db,
            session_id=session_id,
            type="prompt",
            content=config.system_prompt,
            source="user",
            is_valid=True,
            error=None,
        )
    elif config.kind == "pipeline":
        first_llm = next((s for s in config.steps if s.type == "llm"), None)
        if first_llm is not None and first_llm.system_prompt:
            upsert_artifact(
                db,
                session_id=session_id,
                type="prompt",
                content=first_llm.system_prompt,
                source="user",
                is_valid=True,
                error=None,
            )
    if config.code:
        is_valid = True
        error: str | None = None
        try:
            validate_script(config.code)
        except ScriptValidationError as exc:
            is_valid = False
            error = str(exc)
        upsert_artifact(
            db,
            session_id=session_id,
            type="script",
            content=config.code,
            source="user",
            is_valid=is_valid,
            error=error,
        )
    elif config.kind == "pipeline":
        first_script = next((s for s in config.steps if s.type == "script"), None)
        if first_script is not None and first_script.code:
            is_valid = True
            error: str | None = None
            try:
                validate_script(first_script.code)
            except ScriptValidationError as exc:
                is_valid = False
                error = str(exc)
            upsert_artifact(
                db,
                session_id=session_id,
                type="script",
                content=first_script.code,
                source="user",
                is_valid=is_valid,
                error=error,
            )


def _preview(config: SkillConfig) -> SkillPreview:
    """Build the :class:`SkillPreview` shown in the settings modal (CATALOG-6)."""
    return SkillPreview(
        name=config.name,
        description=config.description,
        kind=config.kind,
        model=config.model,
        provider=config.provider,
        reasoning=config.reasoning,
        input_arity=config.input_arity,
        allowed_tools=list(config.allowed_tools),
    )


def _format_skill_for_edit(record: SkillRecord) -> str:
    config = record.config
    lines = [
        f"Редактируем этот скилл: «{record.name}» (id={record.id}, статус={record.status}).",
        "Кратко по мета:",
        f"- name: {config.name}",
        f"- description: {config.description}",
        f"- kind: {config.kind}",
    ]
    if config.kind == "agent":
        lines.append(f"- allowed_tools: {', '.join(config.allowed_tools) or '(нет)'}")
        if config.non_determinism_reason:
            lines.append(f"- non_determinism_reason: {config.non_determinism_reason}")
    if config.kind == "pipeline" and config.steps:
        step_ids = ", ".join(s.id for s in config.steps) or "(нет)"
        lines.append(f"- steps: {step_ids}")
    lines.append(
        f"- input_arity: {config.input_arity if config.input_arity is not None else 'любое'}"
    )
    if config.verify_checks:
        checks = ", ".join(vc.check for vc in config.verify_checks)
        lines.append(f"- verify_checks: {checks}")
    lines.append(
        "Черновик prompt/script уже засеян в панели артефактов "
        "(смотри через read_skill_draft). Не дублируй полный текст в чат."
    )
    lines.append(
        "Обсуди с пользователем изменения и обновляй черновик инструментами "
        "set_skill_meta и save_skill_prompt (для agent) или save_skill_script "
        "(для script) или save_skill_steps (для pipeline)."
    )
    return "\n".join(lines)


@router.post("/skills/{skill_id}/edit", response_model=EditStarted)
async def edit_skill_endpoint(
    skill_id: str, db: Database = Depends(get_workspace_db)
) -> EditStarted:
    """Start an edit session for an existing skill (CATALOG-17).

    Creates a new planning session linked to the skill (``session.skill_id``)
    and seeds it with a human-readable dump of the current config, so the
    planner chat opens already aware of what is being edited. Building from
    this session updates the same skill instead of creating a new one.
    """
    record = get_skill(db, skill_id)
    if record is None:
        raise HTTPException(status_code=404, detail="skill not found")
    session_id = create_session(db, skill_id=skill_id)
    seed_session_artifacts_from_skill(db, session_id, record)
    add_message(
        db,
        session_id=session_id,
        role="assistant",
        content=_format_skill_for_edit(record),
    )
    return EditStarted(session_id=session_id, skill_id=skill_id)


@router.post("/sessions/{session_id}/skill-tracks", response_model=SkillTracksOut)
async def propose_skill_tracks_endpoint(
    request: Request,
    session_id: str,
    db: Database = Depends(get_workspace_db),
    provider: LLMProvider = Depends(get_provider),
    settings: Settings = Depends(get_settings),
) -> SkillTracksOut:
    session_row = get_session(db, session_id)
    if session_row is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session_row.skill_id is not None:
        return SkillTracksOut(tracks=[], skipped=True, fallback=False)
    if _has_track_intent(list_messages(db, session_id)):
        return SkillTracksOut(tracks=[], skipped=True, fallback=False)

    active_model = getattr(request.app.state, "active_model", None)
    model_default = active_model or settings.default_model
    timeout = session_row.llm_timeout_seconds
    try:
        with llm_timeout_context(float(timeout)):
            tracks = await propose_skill_tracks_from_session(
                provider=provider,
                db=db,
                session_id=session_id,
                model_default=model_default,
            )
    except (LLMTimeoutError, RuntimeError):
        return SkillTracksOut(tracks=[], skipped=False, fallback=True)

    if tracks is None:
        return SkillTracksOut(tracks=[], skipped=False, fallback=True)
    return SkillTracksOut(tracks=tracks, skipped=False, fallback=False)


@router.post(
    "/sessions/{session_id}/skill-tracks/select",
    response_model=SkillTrackSelected,
)
async def select_skill_track_endpoint(
    session_id: str,
    req: SkillTrackSelectRequest,
    db: Database = Depends(get_workspace_db),
) -> SkillTrackSelected:
    session_row = get_session(db, session_id)
    if session_row is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session_row.skill_id is not None:
        raise HTTPException(
            status_code=400,
            detail="edit session cannot select skill tracks",
        )
    messages_raw = list_messages(db, session_id)
    for m in messages_raw:
        if (
            m["role"] == "user"
            and isinstance(m["content"], str)
            and m["content"].startswith(TRACK_INTENT_PREFIX)
        ):
            return SkillTrackSelected(
                session_id=session_id, content=m["content"]
            )
    content = _format_track_intent_message(req.track)
    add_message(db, session_id=session_id, role="user", content=content)
    return SkillTrackSelected(session_id=session_id, content=content)


@router.post("/sessions/{session_id}/skills", response_model=SkillBuilt)
async def build_skill_endpoint(
    request: Request,
    session_id: str,
    db: Database = Depends(get_workspace_db),
    provider: LLMProvider = Depends(get_provider),
    tools: ToolRegistry = Depends(get_tools),
    settings: Settings = Depends(get_settings),
) -> SkillBuilt:
    if get_session(db, session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    # CATALOG-14: seed the skill's model from the runtime-selected active model.
    active_model = getattr(request.app.state, "active_model", None)
    skill_id = await build_skill_from_session(
        provider=provider,
        db=db,
        base_tools=tools,
        settings=settings,
        session_id=session_id,
        default_model=active_model,
    )
    record = get_skill(db, skill_id)
    assert record is not None  # just created
    # CATALOG-6: return a preview so the UI opens the settings modal before
    # the user commits, instead of silently dropping a draft.
    return SkillBuilt(skill_id=skill_id, config=_preview(record.config))


@router.patch("/skills/{skill_id}/configure", response_model=SkillBuilt)
async def configure_skill_endpoint(
    skill_id: str,
    req: SkillConfigureRequest,
    db: Database = Depends(get_workspace_db),
) -> SkillBuilt:
    """Apply the user's model/provider/reasoning choices from the settings modal.

    Only fields the user changed are overridden; the rest of the frozen config
    is preserved. The skill must still be a draft (CATALOG-6: configure before
    commit).
    """
    skill = get_skill(db, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="skill not found")
    if skill.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="skill can only be configured while in draft",
        )
    configure_kwargs: dict = {
        "model": req.model,
        "provider": req.provider,
        "reasoning": req.reasoning,
    }
    if "input_arity" in req.model_fields_set:
        configure_kwargs["input_arity"] = req.input_arity
    if req.name is not None:
        configure_kwargs["name"] = req.name
    updated = update_skill_config(db, skill_id, **configure_kwargs)
    assert updated is not None
    return SkillBuilt(skill_id=skill_id, config=_preview(updated.config))


@router.patch("/skills/{skill_id}", response_model=SkillOut)
async def rename_skill_endpoint(
    skill_id: str,
    req: SkillRenameRequest,
    db: Database = Depends(get_workspace_db),
) -> SkillOut:
    skill = get_skill(db, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="skill not found")
    updated = update_skill_config(db, skill_id, name=req.name)
    assert updated is not None
    return SkillOut(
        id=updated.id,
        name=updated.name,
        description=updated.description,
        status=updated.status,
        created_at=updated.created_at,
        kind=updated.config.kind,
        tags=compute_tags(updated.config),
        input_arity=updated.config.input_arity,
    )


@router.post("/skills/{skill_id}/commit", response_model=CommitOut)
async def commit_skill_endpoint(
    skill_id: str, db: Database = Depends(get_workspace_db)
) -> CommitOut:
    skill = get_skill(db, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="skill not found")
    update_status(db, skill_id, "committed")
    return CommitOut(id=skill_id, status="committed")


@router.get("/skills", response_model=list[SkillOut])
async def list_skills_endpoint(
    db: Database = Depends(get_workspace_db), status: str | None = None
) -> list[SkillOut]:
    rows = list_skills(db, status=status)
    return [
        SkillOut(
            id=r["id"],
            name=r["name"],
            description=r["description"],
            status=r["status"],
            created_at=r["created_at"],
            kind=r.get("kind", "agent"),
            tags=r.get("tags", []),
            input_arity=r.get("input_arity"),
            provider=r.get("provider"),
            model=r.get("model"),
            reasoning=r.get("reasoning"),
        )
        for r in rows
    ]


@router.delete("/skills/{skill_id}", status_code=204)
async def delete_skill_endpoint(
    skill_id: str, db: Database = Depends(get_workspace_db)
) -> None:
    if not delete_skill(db, skill_id):
        raise HTTPException(status_code=404, detail="skill not found")
