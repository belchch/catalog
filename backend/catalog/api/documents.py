from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from catalog.api.deps import get_workspace_db, get_workspace
from catalog.api.schemas import DocumentOut
from catalog.documents.ingest import ingest_file, kind_for_filename
from catalog.documents.scan import scan_workspace
from catalog.storage.db import Database
from catalog.storage.repo_document import delete_document, list_documents

router = APIRouter()


@router.post("/documents", response_model=DocumentOut)
async def upload_document(
    file: UploadFile,
    db: Database = Depends(get_workspace_db),
    workspace: str = Depends(get_workspace),
) -> DocumentOut:
    try:
        kind_for_filename(file.filename or "")
        content = await file.read()
        row = ingest_file(db, workspace, filename=file.filename or "upload.md", content=content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DocumentOut(
        id=row.id, title=row.title, kind=row.kind, created_at=row.created_at
    )


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents_endpoint(
    db: Database = Depends(get_workspace_db),
) -> list[DocumentOut]:
    return [
        DocumentOut(
            id=r.id, title=r.title, kind=r.kind, created_at=r.created_at
        )
        for r in list_documents(db)
    ]


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document_endpoint(
    doc_id: str,
    db: Database = Depends(get_workspace_db),
    workspace: str = Depends(get_workspace),
) -> None:
    deleted = delete_document(db, workspace, doc_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="document not found")


@router.post("/documents/reconcile")
async def reconcile_documents_endpoint(
    db: Database = Depends(get_workspace_db),
    workspace: str = Depends(get_workspace),
) -> dict[str, list[str]]:
    report = scan_workspace(db, workspace)
    return {"removed": report.removed}
