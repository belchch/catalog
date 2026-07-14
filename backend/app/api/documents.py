"""``POST/GET /documents`` — upload (md/docx) and list ingested documents."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.api.deps import get_db, get_workspace
from app.api.schemas import DocumentOut
from app.documents.ingest import ingest_file, kind_for_filename
from app.storage.db import Database
from app.storage.repo_document import list_documents

router = APIRouter()


@router.post("/documents", response_model=DocumentOut)
async def upload_document(
    file: UploadFile,
    db: Database = Depends(get_db),
    workspace: str = Depends(get_workspace),
) -> DocumentOut:
    # Validate the extension before reading the body so an unsupported format
    # yields a clear 400 rather than a silent ingest failure.
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
async def list_documents_endpoint(db: Database = Depends(get_db)) -> list[DocumentOut]:
    return [
        DocumentOut(
            id=r.id, title=r.title, kind=r.kind, created_at=r.created_at
        )
        for r in list_documents(db)
    ]
