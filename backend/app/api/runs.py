"""``POST /skills/{id}/apply``, ``GET /runs/{id}``, ``WS /runs/{id}/stream``.

The apply flow is split across two endpoints (step 06): ``POST`` creates the
``skill_run`` row (status ``running``) and returns its id; the WebSocket then
streams the apply loop reusing that same run id (``apply_skill(run_id=...)``),
forwarding every agent/verify event and finishing with an authoritative
``finish`` frame carrying the persisted ``status``/``output_doc_id``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from app.agent.registry import ToolRegistry
from app.api.deps import agent_event_to_frame, get_db
from app.api.schemas import ApplyRequest, RunCreated, RunOut
from app.llm.base import LLMProvider
from app.skills.apply import apply_skill
from app.skills.repo_run import create_run, get_run
from app.skills.repo_skill import get_skill
from app.storage.db import Database

router = APIRouter()


@router.post("/skills/{skill_id}/apply", response_model=RunCreated)
async def apply_endpoint(
    skill_id: str,
    req: ApplyRequest,
    db: Database = Depends(get_db),
) -> RunCreated:
    skill = get_skill(db, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="skill not found")
    if skill.status != "committed":
        raise HTTPException(
            status_code=409,
            detail="skill must be committed before apply",
        )
    run_id = create_run(
        db, skill_id=skill_id, session_id=None, input_doc_id=req.doc_id
    )
    return RunCreated(run_id=run_id)


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run_endpoint(run_id: str, db: Database = Depends(get_db)) -> RunOut:
    row = get_run(db, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    trace: dict | None = None
    if row["trace_json"]:
        import json

        trace = json.loads(row["trace_json"])
    return RunOut(
        id=row["id"],
        skill_id=row["skill_id"],
        input_doc_id=row["input_doc_id"],
        output_doc_id=row["output_doc_id"],
        status=row["status"],
        trace=trace,
    )


@router.websocket("/runs/{run_id}/stream")
async def run_stream_ws(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()

    db: Database = websocket.app.state.db
    provider: LLMProvider = websocket.app.state.provider
    tools: ToolRegistry = websocket.app.state.tools
    workspace: str = websocket.app.state.workspace

    run = get_run(db, run_id)
    if run is None:
        await websocket.send_json({"type": "error", "message": "run not found"})
        await websocket.close()
        return
    if run["status"] != "running":
        await websocket.send_json(
            {"type": "error", "message": f"run is not running (status={run['status']})"}
        )
        await websocket.close()
        return

    skill = get_skill(db, run["skill_id"])
    if skill is None:
        await websocket.send_json({"type": "error", "message": "skill not found"})
        await websocket.close()
        return

    input_doc_id = run["input_doc_id"]
    if not input_doc_id:
        await websocket.send_json(
            {"type": "error", "message": "run has no input document"}
        )
        await websocket.close()
        return

    try:
        async for event in apply_skill(
            provider=provider,
            db=db,
            workspace_dir=workspace,
            skill=skill.config,
            skill_id=run["skill_id"],
            input_doc_id=input_doc_id,
            base_tools=tools,
            run_id=run_id,
        ):
            frame = agent_event_to_frame(event)
            if frame is not None:
                await websocket.send_json(frame)

        # Authoritative finish from the persisted run row.
        final = get_run(db, run_id)
        await websocket.send_json(
            {
                "type": "finish",
                "status": final["status"] if final else "failed",
                "output_doc_id": final["output_doc_id"] if final else None,
            }
        )
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001 — report over the socket, then close
        await websocket.send_json({"type": "error", "message": str(exc)})
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            # Already closed (e.g. client disconnect) — ignore.
            pass
