"""``POST /sessions`` and ``WS /sessions/{id}`` — planner agent loop.

The planner runs the function-calling agent loop (step 03) over the document
tools (``list_documents``/``read_document``) in **collect mode**
(``use_stream=False``) so it can actually inspect documents while planning.
Stream mode in this slice does not parse tool calls (see step 03 note), so the
planner would be unable to read documents there. The final assistant text is
emitted as a single ``token`` frame followed by ``finish`` — recorded here as
the chosen streaming decision (step 06 notes).

CATALOG-11: the WS handler runs the agent loop as an ``asyncio.Task`` and
concurrently listens for a client ``{"type":"cancel"}`` frame. On cancel the
task is cancelled via the standard asyncio mechanism (``CancelledError``
propagates through the whole stack to the LLM call), a ``finish{status:
"cancelled"}`` frame is sent, and the session stays alive for the next
message.
"""

from __future__ import annotations

import asyncio
import json
import re
from contextlib import suppress
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect

from catalog.agent import run_agent
from catalog.agent.events import FinishEvent, ToolResultEvent
from catalog.agent.registry import ToolRegistry
from catalog.api.deps import agent_event_to_frame, get_workspace_db, get_tools
from catalog.api.schemas import (
    ArtifactPatchRequest,
    DocumentOut,
    MessageOut,
    SessionArtifactOut,
    SessionCreated,
    SessionCreateRequest,
    SessionOut,
    SessionToolsAttachRequest,
    SessionToolsAttachResult,
    SessionUpdate,
    SkillMetaPatchRequest,
    SkillOut,
)
from catalog.config import Settings
from catalog.documents.tools import build_document_tools
from catalog.llm.base import LLMProvider, Message
from catalog.llm.log_context import prompt_log_context
from catalog.llm.timeout import DEFAULT_LLM_TIMEOUT_SECONDS, llm_timeout_context
from catalog.skills.artifact_tools import (
    artifacts_frame,
    build_artifact_tools,
    parse_steps_content,
    session_skill_lookup,
    validate_pipeline_steps,
)
from catalog.skills.budget import SkillBudget, estimate_skill_llm_calls, make_turn_budget
from catalog.skills.config import SKILL_KINDS, compute_tags, pipeline_step_to_dict
from catalog.skills.repo_skill import get_skill
from catalog.skills.skill_tools import SkillCallContext, build_session_skill_tools
from catalog.skills.script_runner import (
    SCRIPT_CODE_CONTRACT_RU,
    ScriptValidationError,
    validate_script,
)
from catalog.skills.verify import validate_verify_checks
from catalog.storage.db import Database
from catalog.storage.repo_message import add_message, list_messages
from catalog.storage.repo_session import (
    create_session,
    delete_session,
    get_session,
    list_sessions,
    update_session_llm_timeout,
)
from catalog.storage.repo_session_artifact import (
    ARTIFACT_TYPES,
    list_artifacts,
    upsert_artifact,
)
from catalog.storage.repo_session_document import (
    attach_documents,
    detach_documents,
    list_session_documents,
)
from catalog.storage.repo_session_skill import (
    attach_skills,
    detach_skills,
    list_session_skills,
)


router = APIRouter()

PLANNER_SYSTEM_PROMPT = (
    "Ты — планировщик Catalog. Помогаешь аналитику составить план обработки "
    "документа, который затем превратится в переиспользуемый скилл. "
    "Используй инструменты list_documents и read_document, чтобы изучить "
    "доступные документы. Тебе доступны только документы, явно добавленные "
    "пользователем в эту сессию. Если нужного документа нет в list_documents, "
    "попроси пользователя добавить его — глобальное хранилище тебе недоступно. "
    "Если в сессии прикреплены скиллы-инструменты (имена skill_*), вызывай их "
    "для заранее определённых операций над текстом — они заморожены и проходят "
    "свои verify_checks. "
    "Задавай уточняющие вопросы и формулируй чёткое задание для скилла.\n\n"
    "Когда задача прояснилась — определи kind (agent, script или pipeline) и "
    "материализуй черновик инструментами: set_skill_meta, затем "
    "save_skill_prompt (для agent), save_skill_script (для script) "
    "или save_skill_steps (для pipeline; шаг type=script|llm|skill; "
    "для skill укажи skill_id прикреплённого committed-скилла — id в "
    "списке привязанных скиллов или через list_session_skills; затем "
    "save_skill_script / save_skill_prompt по шагам). "
    "Для kind=script: "
    + SCRIPT_CODE_CONTRACT_RU
    + ". "
    "Поддерживай черновик актуальным через эти инструменты. "
    "Не дублируй полный prompt или script простынёй в чат — они живут в "
    "панели артефактов; в ответе кратко сообщи, что сохранил или обновил "
    "черновик. Читать текущий черновик можно через read_skill_draft.\n\n"
    "В конце КАЖДОГО своего ответа предлагай 1–3 коротких варианта следующего "
    "шага пользователя отдельной строкой строго в формате:\n"
    "<suggestions>вариант 1 | вариант 2 | вариант 3</suggestions>\n"
    "Варианты — конкретные и предельно короткие: до 4 слов и не длиннее 30 "
    "символов каждый, без скобок и уточнений, разделены « | ». "
    "Этот блок вырезается "
    "из текста ответа и показывается пользователю отдельными кнопками, поэтому "
    "не дублируй его содержимое в основном тексте."
)

# Static starter suggestions sent on connect when the session is empty
# (CATALOG-13). Deterministic for now; an LLM-driven source is a future option.
STARTER_SUGGESTIONS = [
    "Изучи доступные документы",
    "Опиши задачу для скилла",
    "Какие документы уже есть?",
]

WS_KEEPALIVE_INTERVAL_S = 30.0

# Matches a ``<suggestions>…</suggestions>`` block (case-insensitive,
# spans newlines). Only the first occurrence is parsed/stripped.
_SUGGESTIONS_RE = re.compile(r"<suggestions>(.*?)</suggestions>", re.IGNORECASE | re.DOTALL)


def parse_suggestions(text: str) -> tuple[str, list[str]]:
    """Extract a ``<suggestions>a | b | c</suggestions>`` block from model text.

    Returns ``(clean_text, items)``: the block is removed from ``clean_text``
    (any trailing whitespace is stripped), and ``items`` is the list of
    stripped, non-empty suggestion strings split on ``|``. If no block is
    present, the text is returned unchanged with an empty list.
    """
    match = _SUGGESTIONS_RE.search(text)
    if match is None:
        return text, []
    items = [s.strip() for s in match.group(1).split("|") if s.strip()]
    clean = (text[: match.start()] + text[match.end() :]).rstrip()
    return clean, items


def _parse_user_payload(raw: str) -> tuple[str, list[str]]:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw, []
    if isinstance(data, dict) and data.get("type") == "user":
        content = str(data.get("content", ""))
        raw_ids = data.get("doc_ids") or []
        doc_ids = (
            [str(d) for d in raw_ids if d]
            if isinstance(raw_ids, list)
            else []
        )
        return content, doc_ids
    if isinstance(data, dict) and isinstance(data.get("content"), str):
        return data["content"], []
    return raw, []


def _planner_system_prompt(db: Database, session_id: str) -> str:
    docs = list_session_documents(db, session_id)
    skills = [
        row
        for row in list_session_skills(db, session_id)
        if row.status == "committed"
    ]
    if not docs and not skills:
        return PLANNER_SYSTEM_PROMPT
    lines = [PLANNER_SYSTEM_PROMPT]
    if docs:
        lines.extend(["", "Привязанные к сессии документы:"])
        for doc in docs:
            lines.append(f"- {doc.id}: {doc.title}")
    if skills:
        lines.extend(
            [
                "",
                "Привязанные к сессии скиллы (для шага type=skill используй skill_id):",
            ]
        )
        for skill in skills:
            lines.append(f"- {skill.id}: {skill.name} ({skill.config.kind})")
    return "\n".join(lines)


def _session_docs_frame(db: Database, session_id: str) -> dict:
    docs = list_session_documents(db, session_id)
    return {
        "type": "session_docs",
        "documents": [
            {
                "id": d.id,
                "title": d.title,
                "kind": d.kind,
                "created_at": d.created_at,
            }
            for d in docs
        ],
    }



def _is_cancel_frame(raw: str) -> bool:
    """Detect a client cancel frame: ``{"type":"cancel"}``."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(data, dict) and data.get("type") == "cancel"


def _is_keepalive_frame(raw: str) -> bool:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(data, dict) and data.get("type") in ("ping", "pong")


async def _receive_text_with_keepalive(websocket: WebSocket) -> str:
    while True:
        receive_task = asyncio.create_task(websocket.receive_text())
        sleep_task = asyncio.create_task(asyncio.sleep(WS_KEEPALIVE_INTERVAL_S))
        try:
            done, pending = await asyncio.wait(
                {receive_task, sleep_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if receive_task in done:
                return receive_task.result()
            await websocket.send_json({"type": "ping"})
        except BaseException:
            receive_task.cancel()
            sleep_task.cancel()
            raise


async def _wait_work_or_ws(
    websocket: WebSocket,
    work_task: asyncio.Task,
    receive_task: asyncio.Task,
) -> tuple[str, str | None]:
    sleep_task = asyncio.create_task(asyncio.sleep(WS_KEEPALIVE_INTERVAL_S))
    try:
        done, _pending = await asyncio.wait(
            {work_task, receive_task, sleep_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if work_task in done:
            return "work", None
        if receive_task in done:
            frame_raw = receive_task.result()
            if _is_cancel_frame(frame_raw):
                return "cancel", frame_raw
            if _is_keepalive_frame(frame_raw):
                return "keepalive", frame_raw
            return "message", frame_raw
        return "ping", None
    finally:
        if not sleep_task.done():
            sleep_task.cancel()
            with suppress(asyncio.CancelledError):
                await sleep_task


def _conversation_messages(db: Database, session_id: str) -> list[Message]:
    """Rebuild the user/assistant conversation from persisted messages."""
    msgs: list[Message] = []
    for m in list_messages(db, session_id):
        if m["role"] in ("user", "assistant") and m["content"] is not None:
            msgs.append(Message(role=m["role"], content=m["content"]))
    return msgs


@router.post("/sessions", response_model=SessionCreated)
async def create_session_endpoint(
    body: Annotated[SessionCreateRequest | None, Body()] = None,
    db: Database = Depends(get_workspace_db),
) -> SessionCreated:
    session_id = create_session(db)
    doc_ids = [doc_id for doc_id in (body.doc_ids if body is not None else []) if doc_id]
    skipped = attach_documents(db, session_id, doc_ids)
    return SessionCreated(id=session_id, skipped_doc_ids=skipped)


def _session_out(row) -> SessionOut:
    return SessionOut(
        id=row.id,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at or row.created_at,
        title=row.title,
        skill_id=row.skill_id,
        llm_timeout_seconds=row.llm_timeout_seconds,
    )


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions_endpoint(
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    db: Database = Depends(get_workspace_db),
) -> list[SessionOut]:
    rows = list_sessions(db, limit=limit, offset=offset, status=status)
    return [_session_out(r) for r in rows]


@router.get("/sessions/{session_id}", response_model=SessionOut)
async def get_session_endpoint(
    session_id: str,
    db: Database = Depends(get_workspace_db),
) -> SessionOut:
    row = get_session(db, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _session_out(row)


@router.patch("/sessions/{session_id}", response_model=SessionOut)
async def update_session_endpoint(
    session_id: str,
    req: SessionUpdate,
    db: Database = Depends(get_workspace_db),
) -> SessionOut:
    row = update_session_llm_timeout(db, session_id, req.llm_timeout_seconds)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _session_out(row)


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
async def list_session_messages_endpoint(
    session_id: str,
    db: Database = Depends(get_workspace_db),
) -> list[MessageOut]:
    if get_session(db, session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    return [MessageOut(**m) for m in list_messages(db, session_id)]


@router.get("/sessions/{session_id}/documents", response_model=list[DocumentOut])
async def list_session_documents_endpoint(
    session_id: str,
    db: Database = Depends(get_workspace_db),
) -> list[DocumentOut]:
    if get_session(db, session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    return [
        DocumentOut(id=d.id, title=d.title, kind=d.kind, created_at=d.created_at)
        for d in list_session_documents(db, session_id)
    ]


@router.delete("/sessions/{session_id}/documents/{doc_id}", status_code=204)
async def detach_session_document_endpoint(
    session_id: str,
    doc_id: str,
    db: Database = Depends(get_workspace_db),
) -> Response:
    if get_session(db, session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    removed = detach_documents(db, session_id, [doc_id])
    if removed == 0:
        raise HTTPException(status_code=404, detail="document not attached")
    return Response(status_code=204)


def _session_skill_out(row) -> SkillOut:
    return SkillOut(
        id=row.id,
        name=row.name,
        description=row.description,
        status=row.status,
        created_at=row.created_at,
        kind=row.config.kind,
        tags=compute_tags(row.config),
        input_arity=row.config.input_arity,
        provider=row.config.provider or None,
        model=row.config.model or None,
        reasoning=row.config.reasoning or None,
        estimated_llm_calls=estimate_skill_llm_calls(row.config),
    )


@router.get("/sessions/{session_id}/tools", response_model=list[SkillOut])
async def list_session_tools_endpoint(
    session_id: str,
    db: Database = Depends(get_workspace_db),
) -> list[SkillOut]:
    if get_session(db, session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    return [_session_skill_out(s) for s in list_session_skills(db, session_id)]


@router.post("/sessions/{session_id}/tools", response_model=SessionToolsAttachResult)
async def attach_session_tools_endpoint(
    session_id: str,
    body: SessionToolsAttachRequest,
    db: Database = Depends(get_workspace_db),
) -> SessionToolsAttachResult:
    if get_session(db, session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    for skill_id in body.skill_ids:
        skill = get_skill(db, skill_id)
        if skill is None:
            continue
        if skill.status == "draft":
            raise HTTPException(
                status_code=422,
                detail=f"cannot attach draft skill {skill_id}",
            )
        if skill.config.kind not in SKILL_KINDS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"cannot attach skill {skill_id} with unknown kind "
                    f"{skill.config.kind!r}"
                ),
            )
    skipped = attach_skills(db, session_id, body.skill_ids)
    return SessionToolsAttachResult(
        skipped_skill_ids=skipped,
        skills=[_session_skill_out(s) for s in list_session_skills(db, session_id)],
    )


@router.delete("/sessions/{session_id}/tools/{skill_id}", status_code=204)
async def detach_session_tool_endpoint(
    session_id: str,
    skill_id: str,
    db: Database = Depends(get_workspace_db),
) -> Response:
    if get_session(db, session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    removed = detach_skills(db, session_id, [skill_id])
    if removed == 0:
        raise HTTPException(status_code=404, detail="skill not attached")
    return Response(status_code=204)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session_endpoint(
    session_id: str,
    db: Database = Depends(get_workspace_db),
) -> Response:
    if not delete_session(db, session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return Response(status_code=204)


def _normalize_meta_input_arity(
    value: object,
) -> tuple[int | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, "input_arity must be 1, 2, or null"
    if isinstance(value, int):
        if value in (1, 2):
            return value, None
        return None, "input_arity must be 1, 2, or null"
    if isinstance(value, str):
        stripped = value.strip()
        if stripped in ("1", "2"):
            return int(stripped), None
    return None, "input_arity must be 1, 2, or null"


def _artifact_out(row) -> SessionArtifactOut:
    return SessionArtifactOut(
        type=row.type,
        content=row.content,
        is_valid=row.is_valid,
        error=row.error,
        source=row.source,
        updated_at=row.updated_at,
    )


@router.get(
    "/sessions/{session_id}/artifacts",
    response_model=list[SessionArtifactOut],
)
async def list_session_artifacts_endpoint(
    session_id: str,
    db: Database = Depends(get_workspace_db),
) -> list[SessionArtifactOut]:
    if get_session(db, session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    return [_artifact_out(r) for r in list_artifacts(db, session_id)]


@router.patch(
    "/sessions/{session_id}/artifacts/{artifact_type}",
    response_model=SessionArtifactOut,
)
async def patch_session_artifact_endpoint(
    session_id: str,
    artifact_type: str,
    req: ArtifactPatchRequest,
    db: Database = Depends(get_workspace_db),
    tools: ToolRegistry = Depends(get_tools),
) -> SessionArtifactOut:
    if get_session(db, session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    if artifact_type not in ARTIFACT_TYPES:
        raise HTTPException(status_code=404, detail="unknown artifact type")
    if artifact_type == "meta":
        try:
            payload = json.loads(req.content)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=422, detail=f"meta content must be JSON: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="meta content must be a JSON object")
        kind = payload.get("kind", "agent")
        raw_allowed = payload.get("allowed_tools", [])
        raw_checks = payload.get("verify_checks", [])
        if raw_allowed is None:
            raw_allowed = []
        if raw_checks is None:
            raw_checks = []
        if not isinstance(raw_allowed, list):
            raise HTTPException(
                status_code=422, detail="allowed_tools must be a list"
            )
        if not isinstance(raw_checks, list):
            raise HTTPException(
                status_code=422, detail="verify_checks must be a list"
            )
        allowed = list(raw_allowed)
        checks = list(raw_checks)
        errors: list[str] = []
        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append("name must be non-empty")
        else:
            payload["name"] = name.strip()
        description = payload.get("description")
        if not isinstance(description, str):
            errors.append("description must be a string")
        else:
            payload["description"] = description
        if "input_arity" in payload:
            arity, arity_error = _normalize_meta_input_arity(payload.get("input_arity"))
            if arity_error is not None:
                errors.append(arity_error)
            else:
                payload["input_arity"] = arity
        if kind not in SKILL_KINDS:
            errors.append(f"unknown skill kind: {kind!r}")
        else:
            if kind == "agent":
                available = set(tools.names())
                for tool_name in allowed:
                    if tool_name not in available:
                        errors.append(f"unknown tool: {tool_name!r}")
            errors.extend(validate_verify_checks(checks))
        payload["allowed_tools"] = allowed if kind == "agent" else []
        payload["verify_checks"] = checks
        row = upsert_artifact(
            db,
            session_id=session_id,
            type="meta",
            content=json.dumps(payload, ensure_ascii=False),
            source="user",
            is_valid=not errors,
            error="; ".join(errors) if errors else None,
        )
        return _artifact_out(row)

    if artifact_type == "steps":
        parsed, errors = parse_steps_content(req.content)
        if not errors:
            attached, lookup = session_skill_lookup(db, session_id)
            errors.extend(
                validate_pipeline_steps(
                    parsed,
                    tools.names(),
                    require_content=False,
                    session_skills=attached,
                    lookup_skill=lookup,
                )
            )
        payload = {"steps": [pipeline_step_to_dict(s) for s in parsed]}
        row = upsert_artifact(
            db,
            session_id=session_id,
            type="steps",
            content=json.dumps(payload, ensure_ascii=False)
            if parsed or not errors
            else req.content,
            source="user",
            is_valid=not errors,
            error="; ".join(errors) if errors else None,
        )
        return _artifact_out(row)

    is_valid = True
    error: str | None = None
    if artifact_type == "script":
        try:
            validate_script(req.content)
        except ScriptValidationError as exc:
            is_valid = False
            error = str(exc)
    elif artifact_type == "prompt":
        if not req.content.strip():
            is_valid = False
            error = "prompt is empty"
    row = upsert_artifact(
        db,
        session_id=session_id,
        type=artifact_type,
        content=req.content,
        source="user",
        is_valid=is_valid,
        error=error,
    )
    return _artifact_out(row)


@router.patch(
    "/sessions/{session_id}/skill-meta",
    response_model=SessionArtifactOut,
)
async def patch_skill_meta_endpoint(
    session_id: str,
    req: SkillMetaPatchRequest,
    db: Database = Depends(get_workspace_db),
    tools: ToolRegistry = Depends(get_tools),
) -> SessionArtifactOut:
    if get_session(db, session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    allowed = list(req.allowed_tools)
    checks = list(req.verify_checks)
    errors: list[str] = []
    if req.kind == "agent":
        available = set(tools.names())
        for name in allowed:
            if name not in available:
                errors.append(f"unknown tool: {name!r}")
    errors.extend(validate_verify_checks(checks))
    payload = {
        "name": req.name,
        "description": req.description,
        "kind": req.kind,
        "input_arity": req.input_arity,
        "allowed_tools": allowed if req.kind == "agent" else [],
        "verify_checks": checks,
    }
    row = upsert_artifact(
        db,
        session_id=session_id,
        type="meta",
        content=json.dumps(payload, ensure_ascii=False),
        source="user",
        is_valid=not errors,
        error="; ".join(errors) if errors else None,
    )
    return _artifact_out(row)


async def _run_planner_turn(
    websocket: WebSocket,
    *,
    provider,
    model: str,
    messages: list[Message],
    tools: ToolRegistry,
    db: Database,
    session_id: str,
    system_prompt: str,
) -> tuple[str | None, bool, bool, str | None]:
    state: dict[str, object] = {"final_text": None, "final_capped": False}

    async def _agent_loop() -> None:
        with prompt_log_context(session_id=session_id, purpose="planner"):
            async for event in run_agent(
                provider=provider,
                model=model,
                system_prompt=system_prompt,
                messages=messages,
                tools=tools,
                use_stream=False,
            ):

                frame = agent_event_to_frame(event)
                if frame is not None:
                    await websocket.send_json(frame)
                if isinstance(event, ToolResultEvent):
                    add_message(
                        db,
                        session_id=session_id,
                        role="tool",
                        content=json.dumps(
                            {"ok": event.ok, "result": event.result},
                            ensure_ascii=False,
                            default=str,
                        ),
                        tool_name=event.name,
                        tool_call_id=event.id,
                    )
                if isinstance(event, FinishEvent):
                    state["final_text"] = event.text
                    state["final_capped"] = event.capped

    agent_task = asyncio.create_task(_agent_loop())
    receive_task = asyncio.create_task(websocket.receive_text())
    cancelled = False
    buffered: str | None = None

    try:
        while True:
            kind, payload = await _wait_work_or_ws(
                websocket, agent_task, receive_task
            )
            if kind == "work":
                receive_task.cancel()
                with suppress(asyncio.CancelledError, WebSocketDisconnect):
                    await receive_task
                agent_task.result()
                break
            if kind == "cancel":
                cancelled = True
                agent_task.cancel()
                with suppress(asyncio.CancelledError):
                    await agent_task
                break
            if kind == "ping":
                await websocket.send_json({"type": "ping"})
                continue
            if kind == "keepalive":
                receive_task = asyncio.create_task(websocket.receive_text())
                continue
            buffered = payload
            receive_task = asyncio.create_task(websocket.receive_text())
    except BaseException:
        agent_task.cancel()
        receive_task.cancel()
        raise

    return (
        str(state["final_text"]) if state["final_text"] is not None else None,
        bool(state["final_capped"]),
        cancelled,
        buffered,
    )


def _ws_session_tools(
    db: Database,
    workspace: str,
    session_id: str,
    base_tools: ToolRegistry,
    websocket: WebSocket,
    provider: LLMProvider | None = None,
    fallback_model: str = "",
    providers: dict[str, LLMProvider] | None = None,
    call_context: SkillCallContext | None = None,
    max_skill_depth: int = 2,
    budget: SkillBudget | None = None,
) -> ToolRegistry:
    tools: ToolRegistry = build_document_tools(db, workspace, session_id)

    async def _notify_artifacts() -> None:
        await websocket.send_json(artifacts_frame(db, session_id))

    artifact_tools = build_artifact_tools(
        db,
        session_id,
        available_tools=base_tools.names(),
        on_artifacts_changed=_notify_artifacts,
    )
    for name in artifact_tools.names():
        entry = artifact_tools.get(name)
        if entry is not None:
            tools.register(entry[0], entry[1])
    skill_tools = build_session_skill_tools(
        db,
        session_id,
        workspace_dir=workspace,
        base_tools=base_tools,
        reserved=set(tools.names()),
        provider=provider,
        fallback_model=fallback_model,
        providers=providers,
        call_context=call_context or SkillCallContext(),
        max_skill_depth=max_skill_depth,
        budget=budget,
    )
    for name in skill_tools.names():
        entry = skill_tools.get(name)
        if entry is not None:
            tools.register(entry[0], entry[1])
    return tools


def _inc_active_planner_turns(state: Any) -> None:
    current = getattr(state, "active_planner_turns", 0)
    state.active_planner_turns = current + 1


def _dec_active_planner_turns(state: Any) -> None:
    current = getattr(state, "active_planner_turns", 0)
    state.active_planner_turns = max(0, current - 1)


@router.websocket("/sessions/{session_id}")
async def session_ws(
    websocket: WebSocket,
    session_id: str,
) -> None:
    await websocket.accept()
    state = websocket.app.state
    settings: Settings = state.settings
    manager = state.workspace_manager
    if manager.current is None or manager.root is None:
        await websocket.send_json({"type": "error", "message": "workspace not open"})
        await websocket.close()
        return

    db = manager.current
    workspace = str(manager.root)
    if get_session(db, session_id) is None:
        await websocket.send_json({"type": "error", "message": "session not found"})
        await websocket.close()
        return

    base_tools: ToolRegistry | None = getattr(state, "tools", None)
    if base_tools is None:
        await websocket.send_json({"type": "error", "message": "workspace not open"})
        await websocket.close()
        return

    if not list_messages(db, session_id):
        await websocket.send_json({"type": "suggestions", "items": STARTER_SUGGESTIONS})

    buffered: str | None = None
    try:
        while True:
            manager = state.workspace_manager
            db = manager.current
            if db is None or manager.root is None:
                await websocket.send_json({"type": "error", "message": "workspace not open"})
                await websocket.close()
                return
            workspace = str(manager.root)
            if get_session(db, session_id) is None:
                await websocket.send_json({"type": "error", "message": "session not found"})
                await websocket.close()
                return
            base_tools = getattr(state, "tools", None)
            if base_tools is None:
                await websocket.send_json({"type": "error", "message": "workspace not open"})
                await websocket.close()
                return

            if buffered is not None:
                raw = buffered
                buffered = None
            else:
                raw = await _receive_text_with_keepalive(websocket)

            if _is_keepalive_frame(raw):
                continue
            if _is_cancel_frame(raw):
                await websocket.send_json({"type": "finish", "status": "noop"})
                continue

            content, doc_ids = _parse_user_payload(raw)
            if doc_ids:
                attach_documents(db, session_id, doc_ids)
                await websocket.send_json(_session_docs_frame(db, session_id))
            add_message(db, session_id=session_id, role="user", content=content)

            messages = _conversation_messages(db, session_id)

            provider = state.provider
            model = (
                getattr(state, "active_model", None)
                or settings.default_model
            )

            session_row = get_session(db, session_id)
            timeout = (
                session_row.llm_timeout_seconds
                if session_row is not None
                else DEFAULT_LLM_TIMEOUT_SECONDS
            )
            budget = make_turn_budget(
                llm_calls_left=settings.skill_budget_llm_calls,
                nested_runs_left=settings.skill_budget_nested_runs,
                llm_timeout_seconds=timeout,
            )
            tools = _ws_session_tools(
                db,
                workspace,
                session_id,
                base_tools,
                websocket,
                provider=state.provider,
                fallback_model=(
                    getattr(state, "active_model", None) or settings.default_model
                ),
                providers=getattr(state, "providers", None),
                call_context=SkillCallContext(),
                max_skill_depth=settings.max_skill_depth,
                budget=budget,
            )
            _inc_active_planner_turns(state)
            try:
                with llm_timeout_context(float(timeout)):
                    final_text, final_capped, cancelled, buffered = await _run_planner_turn(
                        websocket,
                        provider=provider,
                        model=model,
                        messages=messages,
                        tools=tools,
                        db=db,
                        session_id=session_id,
                        system_prompt=_planner_system_prompt(db, session_id),
                    )
            finally:
                _dec_active_planner_turns(state)

            if final_text:
                clean_text, items = parse_suggestions(final_text)
                await websocket.send_json({"type": "token", "delta": clean_text})
                add_message(
                    db,
                    session_id=session_id,
                    role="assistant",
                    content=clean_text,
                )
                if items:
                    await websocket.send_json({"type": "suggestions", "items": items})

            if cancelled:
                await websocket.send_json({"type": "finish", "status": "cancelled"})
                continue

            await websocket.send_json(
                {
                    "type": "finish",
                    "capped": final_capped,
                    "status": "capped" if final_capped else "ok",
                }
            )
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001 — report over the socket, then close
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close()
