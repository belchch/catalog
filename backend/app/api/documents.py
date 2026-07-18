"""``POST/GET/DELETE /documents`` — upload, list, delete; orphan reconcile."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.api.deps import get_db, get_workspace
from app.api.schemas import DocumentOut
from app.documents.ingest import ingest_file, kind_for_filename
from app.storage.db import Database
from app.storage.repo_document import delete_document, list_documents, reconcile_orphans

router = APIRouter()


@router.post("/documents", response_model=DocumentOut)
async def upload_document(
    file: UploadFile,
    db: Database = Depends(get_db),
    workspace: str = Depends(get_workspace),
) -> DocumentOut:
    try:
        kind_for_filename(file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    content = await file.read()
    row = ingest_file(db, workspace, filename=file.filename or "upload.md", content=content)
    return DocumentOut(
        id=row.id, title=row.title, kind=row.kind, created_at=row.created_at
    )


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents_endpoint(
    db: Database = Depends(get_db),
    workspace: str = Depends(get_workspace),
) -> list[DocumentOut]:
    reconcile_orphans(db, workspace)
    return [
        DocumentOut(
            id=r.id, title=r.title, kind=r.kind, created_at=r.created_at
        )
        for r in list_documents(db)
    ]


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document_endpoint(
    doc_id: str,
    db: Database = Depends(get_db),
    workspace: str = Depends(get_workspace),
) -> None:
    deleted = delete_document(db, workspace, doc_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="document not found")


@router.post("/documents/reconcile")
async def reconcile_documents_endpoint(
    db: Database = Depends(get_db),
    workspace: str = Depends(get_workspace),
) -> dict[str, list[str]]:
    removed = reconcile_orphans(db, workspace)
    return {"removed": removed}
