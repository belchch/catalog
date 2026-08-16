from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from catalog.api.deps import get_workspace, get_workspace_db
from catalog.api.schemas import ExportDocxOut, ExportDocxRequest
from catalog.documents.export_docx import write_export_docx
from catalog.storage.db import Database

router = APIRouter()


@router.post("/export/docx", response_model=ExportDocxOut)
async def export_docx_endpoint(
    body: ExportDocxRequest,
    db: Database = Depends(get_workspace_db),
    workspace: str = Depends(get_workspace),
) -> ExportDocxOut:
    result = write_export_docx(
        db,
        workspace,
        body.doc_ids,
        title=body.title,
        template=body.template,
    )
    error = result.get("error")
    if error == "document not found":
        raise HTTPException(status_code=404, detail="document not found")
    if error == "template not found":
        raise HTTPException(status_code=400, detail="template not found")
    if error:
        raise HTTPException(status_code=400, detail=str(error))
    return ExportDocxOut(
        ok=bool(result["ok"]),
        path=str(result["path"]),
        headings=int(result["headings"]),
        tables=int(result["tables"]),
    )
