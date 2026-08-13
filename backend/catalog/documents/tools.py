from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from catalog.agent.registry import ToolRegistry
from catalog.documents.extract import extract_text
from catalog.llm.base import ToolSpec
from catalog.storage.db import Database
from catalog.storage.repo_document import get_document, list_documents, reconcile_orphans
from catalog.storage.repo_session_document import list_session_documents


def build_document_tools(
    db: Database,
    workspace_dir: str | Path,
    session_id: str | None = None,
) -> ToolRegistry:
    workspace = str(workspace_dir)
    reg = ToolRegistry()

    async def _list_documents() -> list[dict[str, str]]:
        reconcile_orphans(db, workspace)
        if session_id is not None:
            rows = list_session_documents(db, session_id)
        else:
            rows = list_documents(db)
        return [
            {"id": row.id, "title": row.title, "kind": row.kind}
            for row in rows
        ]

    async def _read_document(*, doc_id: str) -> dict[str, Any]:
        if session_id is not None:
            attached_ids = {row.id for row in list_session_documents(db, session_id)}
            if doc_id not in attached_ids:
                return {"error": "document_not_available_in_session"}
        row = get_document(db, doc_id)
        if row is None:
            return {"error": "document not found"}
        text = extract_text(os.path.join(workspace, row.path), row.kind)
        return {"title": row.title, "kind": row.kind, "text": text}

    scope_note = (
        " Scope: only documents attached to the current session."
        if session_id is not None
        else ""
    )
    reg.register(
        ToolSpec(
            name="list_documents",
            description=(
                "List ingested documents with their id, title and kind."
                + scope_note
            ),
            parameters={"type": "object", "properties": {}},
        ),
        _list_documents,
    )
    reg.register(
        ToolSpec(
            name="read_document",
            description=(
                "Read the full text of a document by its id."
                + scope_note
            ),
            parameters={
                "type": "object",
                "properties": {"doc_id": {"type": "string"}},
                "required": ["doc_id"],
            },
        ),
        _read_document,
    )
    return reg
