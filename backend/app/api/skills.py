"""``POST /sessions/{id}/skills`` (build), ``POST /skills/{id}/commit``,
``POST /skills/{id}/edit``, ``GET /skills``.

``build_skill_from_session`` makes a single function-calling LLM turn with a
``build_skill`` tool whose schema mirrors :class:`SkillConfig`. The returned
arguments are validated (``allowed_tools`` must exist in the registry;
``verify_checks`` ids must be registered) and retried up to twice with feedback
before the skill is persisted as ``draft`` (ADR-0004: build at approval).

CATALOG-17: when the build's session was started via ``POST
/skills/{id}/edit`` (``session.skill_id`` set), the same skill is updated in
place (``update_skill``) instead of a new one being created — a committed
skill drops back to ``draft``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_db, get_provider, get_settings, get_tools
from app.api.schemas import (
    CommitOut,
    EditStarted,
    SkillBuilt,
    SkillConfigureRequest,
    SkillOut,
    SkillPreview,
    SkillRenameRequest,
)
from app.config import Settings
from app.llm.base import LLMProvider, Message, ToolSpec
from app.llm.log_context import prompt_log_context
from app.agent.registry import ToolRegistry
from app.skills.config import SkillConfig, VerifyCheck, compute_tags
from app.skills.repo_skill import (
    SkillRecord,
    create_skill,
    delete_skill,
    get_skill,
    list_skills,
    update_skill,
    update_status,
    update_skill_config,
)
from app.skills.script_runner import ScriptValidationError, validate_script
from app.skills.verify import registered_checks
from app.storage.db import Database
from app.storage.repo_message import add_message, list_messages
from app.storage.repo_session import create_session, get_session, update_session_status

router = APIRouter()

MAX_BUILD_ATTEMPTS = 3  # 1 initial + 2 retries (step 06 contract).

BUILD_SKILL_SYSTEM_PROMPT = (
    "Ты собираешь SkillConfig из истории планировочной сессии. "
    "СНАЧАЛА оцени детерминизм задачи. Если задача сводится к чистой обработке "
    "текста/данных без суждений и рассуждений (форматирование, подсчёт, "
    "регулярные преобразования, парсинг, сортировка) — выбери kind=\"script\" "
    "и напиши валидный Python-код в поле code: без import, без open/eval/exec; "
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
                "Python source for kind=script skills. No import/open/eval/exec; "
                "input via `document`/`documents`; output via "
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
    if kind == "script":
        allowed_tools: list[str] = []
    else:
        allowed_tools = list(args.get("allowed_tools") or [])
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
    if config.kind not in ("agent", "script"):
        errors.append(f"unknown skill kind: {config.kind!r} (expected 'agent' or 'script')")
        return errors
    if config.kind == "script":
        try:
            validate_script(config.code)
        except ScriptValidationError as exc:
            errors.append(str(exc))
    else:
        for name in config.allowed_tools:
            if name not in available_tools:
                errors.append(f"unknown tool: {name!r}")
    # Verify-check ids are validated for both kinds (a script may have checks).
    for vc in config.verify_checks:
        if vc.check not in available_checks:
            errors.append(f"unknown verify check: {vc.check!r}")
    return errors


async def build_skill_from_session(
    *,
    provider: LLMProvider,
    db: Database,
    base_tools: ToolRegistry,
    settings: Settings,
    session_id: str,
    default_model: str | None = None,
) -> str:
    """Build a draft skill from a session; return the new skill id.

    Raises :class:`HTTPException` (422) if no valid config can be produced
    within the retry budget.

    ``default_model`` (CATALOG-14) overrides the frozen ``settings.default_model``
    so a skill is seeded from the runtime-selected model when set.
    """
    model_default = default_model or settings.default_model
    messages_raw = list_messages(db, session_id)
    history: list[Message] = [Message(role="system", content=BUILD_SKILL_SYSTEM_PROMPT)]
    for m in messages_raw:
        if m["role"] in ("user", "assistant") and m["content"] is not None:
            history.append(Message(role=m["role"], content=m["content"]))

    available_tools = base_tools.names()
    available_checks = registered_checks()

    # Tag every LLM call in the build loop with the session + purpose so the
    # prompt log can correlate build attempts back to a session.
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

            # CATALOG-17: an edit session (``session.skill_id`` set) updates
            # the existing skill in place instead of creating a new one. A
            # committed skill drops back to draft (it needs a fresh commit);
            # a draft edited skill stays draft.
            session_row = get_session(db, session_id)
            edit_target = session_row.skill_id if session_row is not None else None
            if edit_target is not None:
                existing = get_skill(db, edit_target)
                if existing is None:
                    raise HTTPException(
                        status_code=404, detail="edited skill not found"
                    )
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

    raise HTTPException(
        status_code=422,
        detail="failed to build a valid skill after retries",
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
    """Human-readable dump of a skill's current config for the edit prefill.

    Seeds the planning session so the planner (and, later, ``build_skill``)
    has the full existing config in context instead of starting from a blank
    session (CATALOG-17).
    """
    config = record.config
    lines = [
        f"Редактируем этот скилл: «{record.name}» (id={record.id}, статус={record.status}).",
        "Текущая конфигурация:",
        f"- name: {config.name}",
        f"- description: {config.description}",
        f"- kind: {config.kind}",
    ]
    if config.kind == "script":
        lines.append(f"- code:\n{config.code}")
    else:
        lines.append(f"- system_prompt: {config.system_prompt}")
        lines.append(f"- allowed_tools: {', '.join(config.allowed_tools) or '(нет)'}")
        lines.append(f"- model: {config.model}")
        if config.provider:
            lines.append(f"- provider: {config.provider}")
        if config.reasoning:
            lines.append(f"- reasoning: {config.reasoning}")
        if config.non_determinism_reason:
            lines.append(f"- non_determinism_reason: {config.non_determinism_reason}")
    lines.append(f"- input_arity: {config.input_arity if config.input_arity is not None else 'любое'}")
    if config.verify_checks:
        checks = ", ".join(vc.check for vc in config.verify_checks)
        lines.append(f"- verify_checks: {checks}")
    lines.append(
        "Обсуди с пользователем, что нужно изменить, и вызови build_skill "
        "заново с обновлённой конфигурацией, когда всё согласовано."
    )
    return "\n".join(lines)


@router.post("/skills/{skill_id}/edit", response_model=EditStarted)
async def edit_skill_endpoint(
    skill_id: str, db: Database = Depends(get_db)
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
    add_message(
        db,
        session_id=session_id,
        role="assistant",
        content=_format_skill_for_edit(record),
    )
    return EditStarted(session_id=session_id, skill_id=skill_id)


@router.post("/sessions/{session_id}/skills", response_model=SkillBuilt)
async def build_skill_endpoint(
    request: Request,
    session_id: str,
    db: Database = Depends(get_db),
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
    db: Database = Depends(get_db),
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
    db: Database = Depends(get_db),
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
    skill_id: str, db: Database = Depends(get_db)
) -> CommitOut:
    skill = get_skill(db, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="skill not found")
    update_status(db, skill_id, "committed")
    return CommitOut(id=skill_id, status="committed")


@router.get("/skills", response_model=list[SkillOut])
async def list_skills_endpoint(
    db: Database = Depends(get_db), status: str | None = None
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
        )
        for r in rows
    ]


@router.delete("/skills/{skill_id}", status_code=204)
async def delete_skill_endpoint(
    skill_id: str, db: Database = Depends(get_db)
) -> None:
    if not delete_skill(db, skill_id):
        raise HTTPException(status_code=404, detail="skill not found")
