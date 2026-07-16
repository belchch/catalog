"""``POST /sessions/{id}/skills`` (build), ``POST /skills/{id}/commit``,
``GET /skills``.

``build_skill_from_session`` makes a single function-calling LLM turn with a
``build_skill`` tool whose schema mirrors :class:`SkillConfig`. The returned
arguments are validated (``allowed_tools`` must exist in the registry;
``verify_checks`` ids must be registered) and retried up to twice with feedback
before the skill is persisted as ``draft`` (ADR-0004: build at approval).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_db, get_provider, get_settings, get_tools
from app.api.schemas import CommitOut, SkillBuilt, SkillOut
from app.config import Settings
from app.llm.base import LLMProvider, Message, ToolSpec
from app.llm.log_context import prompt_log_context
from app.agent.registry import ToolRegistry
from app.skills.config import SkillConfig, VerifyCheck
from app.skills.repo_skill import create_skill, get_skill, list_skills, update_status
from app.skills.script_runner import ScriptValidationError, validate_script
from app.skills.verify import registered_checks
from app.storage.db import Database
from app.storage.repo_message import list_messages
from app.storage.repo_session import get_session, update_session_status

router = APIRouter()

MAX_BUILD_ATTEMPTS = 3  # 1 initial + 2 retries (step 06 contract).

BUILD_SKILL_SYSTEM_PROMPT = (
    "Ты собираешь SkillConfig из истории планировочной сессии. "
    "СНАЧАЛА оцени детерминизм задачи. Если задача сводится к чистой обработке "
    "текста/данных без суждений и рассуждений (форматирование, подсчёт, "
    "регулярные преобразования, парсинг, сортировка) — выбери kind=\"script\" "
    "и напиши валидный Python-код в поле code: без import, без open/eval/exec; "
    "входной текст документа доступен в переменной document; результат "
    "возвращается через return из функции main(), через присваивание глобальной "
    "переменной result или через print. Если задача требует суждений, "
    "рассуждений или творческой обработки — выбери kind=\"agent\" и ОБЯЗАТЕЛЬНО "
    "заполни non_determinism_reason объяснением, почему детерминизм невозможен. "
    "Для agent также заполни system_prompt (полная инструкция агенту), "
    "allowed_tools (только из доступных инструментов), model, verify_checks "
    "(только из реестра проверок)."
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
                "input in `document`; output via main()/result/print."
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
) -> str:
    """Build a draft skill from a session; return the new skill id.

    Raises :class:`HTTPException` (422) if no valid config can be produced
    within the retry budget.
    """
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
                settings.default_model,
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
                config = _args_to_config(tc.arguments, settings.default_model)
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


@router.post("/sessions/{session_id}/skills", response_model=SkillBuilt)
async def build_skill_endpoint(
    session_id: str,
    db: Database = Depends(get_db),
    provider: LLMProvider = Depends(get_provider),
    tools: ToolRegistry = Depends(get_tools),
    settings: Settings = Depends(get_settings),
) -> SkillBuilt:
    if get_session(db, session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    skill_id = await build_skill_from_session(
        provider=provider,
        db=db,
        base_tools=tools,
        settings=settings,
        session_id=session_id,
    )
    return SkillBuilt(skill_id=skill_id)


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
        )
        for r in rows
    ]
