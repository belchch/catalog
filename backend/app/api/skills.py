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
from app.agent.registry import ToolRegistry
from app.skills.config import SkillConfig, VerifyCheck
from app.skills.repo_skill import create_skill, get_skill, list_skills, update_status
from app.skills.verify import registered_checks
from app.storage.db import Database
from app.storage.repo_message import list_messages
from app.storage.repo_session import get_session, update_session_status

router = APIRouter()

MAX_BUILD_ATTEMPTS = 3  # 1 initial + 2 retries (step 06 contract).

BUILD_SKILL_SYSTEM_PROMPT = (
    "Ты собираешь SkillConfig — замороженный конфиг агента — из истории "
    "планировочной сессии. Вызови инструмент build_skill с полями конфига: "
    "name, description, system_prompt, allowed_tools (только из доступных "
    "инструментов), model, temperature, verify_checks (только из реестра "
    "проверок). system_prompt должен быть полной инструкцией для агента, "
    "который будет применять скилл к документу."
)

# JSON-Schema for the build_skill tool arguments, mirroring SkillConfig fields.
_BUILD_SKILL_PARAMETERS = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
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
    "required": ["name", "description", "system_prompt", "allowed_tools", "model"],
}

BUILD_SKILL_TOOL = ToolSpec(
    name="build_skill",
    description="Build a skill configuration (SkillConfig) from the session history.",
    parameters=_BUILD_SKILL_PARAMETERS,
)


def _args_to_config(args: dict, default_model: str) -> SkillConfig:
    """Parse ``build_skill`` tool arguments into a :class:`SkillConfig`."""
    verify_checks = [
        VerifyCheck(
            check=vc["check"],
            params=dict(vc.get("params", {})),
        )
        for vc in (args.get("verify_checks") or [])
    ]
    return SkillConfig(
        name=args["name"],
        description=args["description"],
        system_prompt=args["system_prompt"],
        allowed_tools=list(args.get("allowed_tools") or []),
        model=args.get("model") or default_model,
        temperature=float(args.get("temperature", 0.0)),
        max_iterations=int(args.get("max_iterations", 8)),
        max_retries=int(args.get("max_retries", 2)),
        verify_checks=verify_checks,
        output_kind=args.get("output_kind", "md"),
    )


def _validate_config(
    config: SkillConfig, available_tools: list[str], available_checks: list[str]
) -> list[str]:
    """Return a list of validation errors (empty when the config is valid)."""
    errors: list[str] = []
    for name in config.allowed_tools:
        if name not in available_tools:
            errors.append(f"unknown tool: {name!r}")
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
        )
        for r in rows
    ]
