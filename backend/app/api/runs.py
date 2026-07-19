"""``POST /skills/{id}/apply``, ``GET /runs/{id}``, ``WS /runs/{id}/stream``,
``POST /runs/{id}/save``.

The apply flow is split across two endpoints (step 06): ``POST`` creates the
``skill_run`` row (status ``running``) and returns its id; the WebSocket then
streams the apply loop reusing that same run id (``apply_skill(run_id=...)``),
forwarding every agent/verify event and finishing with an authoritative
``finish`` frame carrying the persisted ``status``/``output_doc_id``/
``result_text``.

CATALOG-11: the apply stream runs as an ``asyncio.Task`` with a concurrent
cancel listener. On ``{"type":"cancel"}`` the task is cancelled; ``apply_skill``
catches ``CancelledError`` and marks the run ``cancelled`` (not ``failed``),
so the authoritative ``finish`` frame carries ``status:"cancelled"``.

CATALOG-18: ``ApplyRequest.persist`` selects the output mode ("в док" vs "на
экран"); ``POST /runs/{id}/save`` materializes a ``persist=False`` run's
on-screen ``result_text`` into a ``result_md`` document after the fact.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from app.agent.registry import ToolRegistry
from app.api.deps import agent_event_to_frame, get_db, get_workspace
from app.api.schemas import ApplyRequest, DocumentOut, RunCreated, RunOut
from app.api.sessions import _is_cancel_frame
from app.documents.ingest import build_doc_path
from app.documents.obsidian import build_title_to_stem_map, rewrite_wiki_links
from app.documents.tools import build_document_tools
from app.llm.base import LLMProvider
from app.llm.factory import provider_for_skill, provider_name_for_skill
from app.llm.log_context import prompt_log_context
from app.skills.apply import apply_skill
from app.skills.repo_run import create_run, get_run, set_output_doc_id
from app.skills.repo_skill import get_skill
from app.storage.db import Database
from app.storage.repo_document import create_document
from app.storage.repo_session_document import attach_documents

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
    # Arity check (CATALOG-4): a skill may declare how many inputs it expects.
    doc_ids = req.doc_ids
    if skill.config.input_arity is not None and len(doc_ids) != skill.config.input_arity:
        raise HTTPException(
            status_code=422,
            detail=(
                f"skill expects {skill.config.input_arity} input document(s), "
                f"got {len(doc_ids)}"
            ),
        )
    run_id = create_run(
        db,
        skill_id=skill_id,
        session_id=req.session_id,
        input_doc_ids=doc_ids,
        persist=req.persist,
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
        input_doc_ids=row["input_doc_ids"],
        output_doc_id=row["output_doc_id"],
        status=row["status"],
        trace=trace,
        result_text=row["result_text"],
    )


@router.post("/runs/{run_id}/save", response_model=DocumentOut)
async def save_run_result_endpoint(
    run_id: str,
    db: Database = Depends(get_db),
    workspace: str = Depends(get_workspace),
) -> DocumentOut:
    """Materialize a finished run's on-screen result into a document (CATALOG-18).

    Used by the "Сохранить как новый документ" button after a ``persist=False``
    ("на экран") apply: the run must have finished successfully with a
    non-empty ``result_text`` and no ``output_doc_id`` yet (a ``persist=True``
    run already has one — saving again would create a duplicate).
    """
    run = get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if run["output_doc_id"]:
        raise HTTPException(status_code=409, detail="run result is already saved")
    if run["status"] != "ok" or not run["result_text"]:
        raise HTTPException(status_code=409, detail="run has no result to save")

    skill = get_skill(db, run["skill_id"])
    title = f"{skill.name} — результат" if skill is not None else "Результат прогона"
    out_id = uuid.uuid4().hex
    rel_path = build_doc_path(title, out_id, ".md", "results")
    doc = create_document(
        db, title=title, path=rel_path, kind="result_md", doc_id=out_id
    )
    results_dir = Path(workspace) / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    file_text = rewrite_wiki_links(
        run["result_text"], build_title_to_stem_map(db)
    )
    (Path(workspace) / rel_path).write_text(file_text, encoding="utf-8")
    set_output_doc_id(db, run_id, out_id)
    if run["session_id"] is not None:
        attach_documents(db, run["session_id"], [out_id])

    return DocumentOut(id=doc.id, title=doc.title, kind=doc.kind, created_at=doc.created_at)


@router.websocket("/runs/{run_id}/stream")
async def run_stream_ws(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()

    db: Database = websocket.app.state.db
    provider: LLMProvider = websocket.app.state.provider
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

    input_doc_ids = run["input_doc_ids"]
    if not input_doc_ids:
        await websocket.send_json(
            {"type": "error", "message": "run has no input document"}
        )
        await websocket.close()
        return

    session_id = run["session_id"]
    if session_id is not None:
        tools: ToolRegistry = build_document_tools(db, workspace, session_id)
    else:
        tools = websocket.app.state.tools

    # CATALOG-6: honour a provider pinned on the skill (set in the settings
    # modal); fall back to the app's active provider otherwise.
    providers = getattr(websocket.app.state, "providers", None)
    apply_provider = provider_for_skill(
        providers, provider, skill.config.provider
    )
    # CATALOG-16: the resolved provider name is surfaced via the opening
    # RunMetaEvent so the trace feed can show *which* provider ran. The name
    # follows the same pin/fallback rule as the provider instance above
    # (provider_name_for_skill), avoiding a second copy of the condition.
    resolved_provider_name = provider_name_for_skill(
        providers,
        getattr(websocket.app.state, "active_provider", "") or "",
        skill.config.provider,
    )

    try:
        # Bind run_id/purpose so every log line and prompt-log entry for this
        # apply stream carries the correlation context (iteration is set per
        # turn inside _run_agent_core).
        with prompt_log_context(
            run_id=run_id, session_id=session_id, purpose="apply_skill"
        ):
            apply_task = asyncio.create_task(
                _stream_apply(
                    websocket,
                    provider=apply_provider,
                    db=db,
                    workspace_dir=workspace,
                    skill=skill.config,
                    skill_id=run["skill_id"],
                    input_doc_ids=input_doc_ids,
                    base_tools=tools,
                    run_id=run_id,
                    session_id=session_id,
                    provider_name=resolved_provider_name,
                    persist=run["persist"],
                )
            )
            receive_task = asyncio.create_task(websocket.receive_text())

            try:
                while True:
                    done, _pending = await asyncio.wait(
                        {apply_task, receive_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if receive_task in done:
                        frame_raw = receive_task.result()
                        if _is_cancel_frame(frame_raw):
                            apply_task.cancel()
                            try:
                                await apply_task
                            except asyncio.CancelledError:
                                pass
                            break
                        # Non-cancel frame during apply: keep listening.
                        receive_task = asyncio.create_task(
                            websocket.receive_text()
                        )
                    if apply_task in done:
                        receive_task.cancel()
                        try:
                            await receive_task
                        except (asyncio.CancelledError, WebSocketDisconnect):
                            pass
                        apply_task.result()
                        break
            except BaseException:
                apply_task.cancel()
                receive_task.cancel()
                raise

        # Authoritative finish from the persisted run row. On cancel the row
        # was marked ``cancelled`` by apply_skill's CancelledError handler.
        final = get_run(db, run_id)
        await websocket.send_json(
            {
                "type": "finish",
                "status": final["status"] if final else "failed",
                "output_doc_id": final["output_doc_id"] if final else None,
                "result_text": final["result_text"] if final else None,
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


async def _stream_apply(
    websocket: WebSocket,
    *,
    provider: LLMProvider,
    db: Database,
    workspace_dir: str,
    skill,
    skill_id: str,
    input_doc_ids: list[str],
    base_tools: ToolRegistry,
    run_id: str,
    session_id: str | None = None,
    provider_name: str,
    persist: bool = True,
) -> None:
    """Drive ``apply_skill`` and forward every event frame to the socket."""
    async for event in apply_skill(
        provider=provider,
        db=db,
        workspace_dir=workspace_dir,
        skill=skill,
        skill_id=skill_id,
        input_doc_ids=input_doc_ids,
        base_tools=base_tools,
        run_id=run_id,
        session_id=session_id,
        provider_name=provider_name,
        persist=persist,
    ):
        frame = agent_event_to_frame(event)
        if frame is not None:
            await websocket.send_json(frame)
