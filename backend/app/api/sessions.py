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

from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect

from app.agent import run_agent
from app.agent.events import FinishEvent, ToolResultEvent
from app.agent.registry import ToolRegistry
from app.api.deps import agent_event_to_frame, get_db
from app.api.schemas import MessageOut, SessionCreated, SessionOut
from app.config import Settings
from app.llm.base import Message
from app.llm.log_context import prompt_log_context
from app.storage.db import Database
from app.storage.repo_message import add_message, list_messages
from app.storage.repo_session import (
    create_session,
    delete_session,
    get_session,
    list_sessions,
)

router = APIRouter()

PLANNER_SYSTEM_PROMPT = (
    "Ты — планировщик Catalog. Помогаешь аналитику составить план обработки "
    "документа, который затем превратится в переиспользуемый скилл. "
    "Используй инструменты list_documents и read_document, чтобы изучить "
    "доступные документы. Задавай уточняющие вопросы и формулируй чёткое "
    "задание для скилла.\n\n"
    "В конце КАЖДОГО своего ответа предлагай 1–3 коротких варианта следующего "
    "шага пользователя отдельной строкой строго в формате:\n"
    "<suggestions>вариант 1 | вариант 2 | вариант 3</suggestions>\n"
    "Варианты — конкретные, до 6 слов, разделены « | ». Этот блок вырезается "
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


def _parse_user_payload(raw: str) -> str:
    """Accept either plain text or ``{"type":"user","content":"..."}`` JSON."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
    if isinstance(data, dict) and data.get("type") == "user":
        return str(data.get("content", ""))
    if isinstance(data, dict) and isinstance(data.get("content"), str):
        return data["content"]
    return raw


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


def _conversation_messages(db: Database, session_id: str) -> list[Message]:
    """Rebuild the user/assistant conversation from persisted messages."""
    msgs: list[Message] = []
    for m in list_messages(db, session_id):
        if m["role"] in ("user", "assistant") and m["content"] is not None:
            msgs.append(Message(role=m["role"], content=m["content"]))
    return msgs


@router.post("/sessions", response_model=SessionCreated)
async def create_session_endpoint(db: Database = Depends(get_db)) -> SessionCreated:
    return SessionCreated(id=create_session(db))


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions_endpoint(
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    db: Database = Depends(get_db),
) -> list[SessionOut]:
    rows = list_sessions(db, limit=limit, offset=offset, status=status)
    return [
        SessionOut(
            id=r.id,
            status=r.status,
            created_at=r.created_at,
            updated_at=r.updated_at or r.created_at,
            title=r.title,
            skill_id=r.skill_id,
        )
        for r in rows
    ]


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
async def list_session_messages_endpoint(
    session_id: str,
    db: Database = Depends(get_db),
) -> list[MessageOut]:
    if get_session(db, session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    return [MessageOut(**m) for m in list_messages(db, session_id)]


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session_endpoint(
    session_id: str,
    db: Database = Depends(get_db),
) -> Response:
    if not delete_session(db, session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return Response(status_code=204)


async def _run_planner_turn(
    websocket: WebSocket,
    *,
    provider,
    model: str,
    messages: list[Message],
    tools: ToolRegistry,
    db: Database,
    session_id: str,
) -> tuple[str | None, bool, bool, str | None]:
    """Run one planner agent turn, streaming frames, concurrently with a cancel listener.

    Returns ``(final_text, final_capped, cancelled, buffered_frame)``. The
    ``buffered_frame`` is a non-cancel client frame that arrived while the agent
    was running (the UI normally disables input during streaming, but we hold
    onto one such frame so it is not silently lost).
    """
    state: dict[str, object] = {"final_text": None, "final_capped": False}

    async def _agent_loop() -> None:
        with prompt_log_context(session_id=session_id, purpose="planner"):
            async for event in run_agent(
                provider=provider,
                model=model,
                system_prompt=PLANNER_SYSTEM_PROMPT,
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
            done, _pending = await asyncio.wait(
                {agent_task, receive_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if receive_task in done:
                # receive_text() raises WebSocketDisconnect on close — propagate.
                frame_raw = receive_task.result()
                if _is_cancel_frame(frame_raw):
                    cancelled = True
                    agent_task.cancel()
                    try:
                        await agent_task
                    except asyncio.CancelledError:
                        pass
                    break
                # A non-cancel frame arrived mid-turn: buffer it for the next
                # loop iteration and keep listening for a cancel.
                buffered = frame_raw
                receive_task = asyncio.create_task(websocket.receive_text())
            if agent_task in done:
                receive_task.cancel()
                try:
                    await receive_task
                except (asyncio.CancelledError, WebSocketDisconnect):
                    pass
                # Surface any agent exception to the outer handler.
                agent_task.result()
                break
    except BaseException:
        # Ensure both tasks are cleaned up on disconnect/error.
        agent_task.cancel()
        receive_task.cancel()
        raise

    return (
        str(state["final_text"]) if state["final_text"] is not None else None,
        bool(state["final_capped"]),
        cancelled,
        buffered,
    )


@router.websocket("/sessions/{session_id}")
async def session_ws(
    websocket: WebSocket,
    session_id: str,
) -> None:
    await websocket.accept()

    db: Database = websocket.app.state.db
    tools: ToolRegistry = websocket.app.state.tools
    settings: Settings = websocket.app.state.settings

    if get_session(db, session_id) is None:
        await websocket.send_json({"type": "error", "message": "session not found"})
        await websocket.close()
        return

    # CATALOG-13: starter suggestions for an empty session so the chat shows
    # quick-reply buttons before the first message.
    if not list_messages(db, session_id):
        await websocket.send_json({"type": "suggestions", "items": STARTER_SUGGESTIONS})

    buffered: str | None = None
    try:
        while True:
            if buffered is not None:
                raw = buffered
                buffered = None
            else:
                raw = await _receive_text_with_keepalive(websocket)

            if _is_cancel_frame(raw) or _is_keepalive_frame(raw):
                continue

            content = _parse_user_payload(raw)
            add_message(db, session_id=session_id, role="user", content=content)

            messages = _conversation_messages(db, session_id)

            # CATALOG-14: read the runtime active provider/model each turn so a
            # mid-session UI switch takes effect immediately.
            provider = websocket.app.state.provider
            model = (
                getattr(websocket.app.state, "active_model", None)
                or settings.default_model
            )

            final_text, final_capped, cancelled, buffered = await _run_planner_turn(
                websocket,
                provider=provider,
                model=model,
                messages=messages,
                tools=tools,
                db=db,
                session_id=session_id,
            )

            # Emit the final assistant text as a single token frame (collect
            # mode does not stream tokens incrementally — see module docstring).
            # CATALOG-13: strip the <suggestions> block from the shown/persisted
            # text and emit it as a separate suggestions frame before finish.
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
