"""``POST /sessions`` and ``WS /sessions/{id}`` — planner agent loop.

The planner runs the function-calling agent loop (step 03) over the document
tools (``list_documents``/``read_document``) in **collect mode**
(``use_stream=False``) so it can actually inspect documents while planning.
Stream mode in this slice does not parse tool calls (see step 03 note), so the
planner would be unable to read documents there. The final assistant text is
emitted as a single ``token`` frame followed by ``finish`` — recorded here as
the chosen streaming decision (step 06 notes).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.agent import run_agent
from app.agent.events import FinishEvent, ToolResultEvent
from app.agent.registry import ToolRegistry
from app.api.deps import agent_event_to_frame, get_db
from app.api.schemas import SessionCreated
from app.config import Settings
from app.llm.base import LLMProvider, Message
from app.llm.log_context import prompt_log_context
from app.storage.db import Database
from app.storage.repo_message import add_message, list_messages
from app.storage.repo_session import create_session, get_session

router = APIRouter()

PLANNER_SYSTEM_PROMPT = (
    "Ты — планировщик Catalog. Помогаешь аналитику составить план обработки "
    "документа, который затем превратится в переиспользуемый скилл. "
    "Используй инструменты list_documents и read_document, чтобы изучить "
    "доступные документы. Задавай уточняющие вопросы и формулируй чёткое "
    "задание для скилла."
)


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


@router.websocket("/sessions/{session_id}")
async def session_ws(
    websocket: WebSocket,
    session_id: str,
) -> None:
    await websocket.accept()

    db: Database = websocket.app.state.db
    provider: LLMProvider = websocket.app.state.provider
    tools: ToolRegistry = websocket.app.state.tools
    settings: Settings = websocket.app.state.settings

    if get_session(db, session_id) is None:
        await websocket.send_json({"type": "error", "message": "session not found"})
        await websocket.close()
        return

    try:
        while True:
            raw = await websocket.receive_text()
            content = _parse_user_payload(raw)
            add_message(db, session_id=session_id, role="user", content=content)

            messages = _conversation_messages(db, session_id)
            final_text: str | None = None
            final_capped = False

            # Bind the planner session to the prompt-log context so every LLM
            # call inside run_agent is tagged with session_id + purpose.
            with prompt_log_context(session_id=session_id, purpose="planner"):
                async for event in run_agent(
                    provider=provider,
                    model=settings.default_model,
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
                        final_text = event.text
                        final_capped = event.capped

            # Emit the final assistant text as a single token frame (collect
            # mode does not stream tokens incrementally — see module docstring).
            if final_text:
                await websocket.send_json({"type": "token", "delta": final_text})
                add_message(
                    db, session_id=session_id, role="assistant", content=final_text
                )

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
