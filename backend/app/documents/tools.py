from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.agent.registry import ToolRegistry
from app.documents.extract import extract_text
from app.llm.base import ToolSpec
from app.storage.db import Database
from app.storage.repo_document import get_document, list_documents


def build_document_tools(db: Database, workspace_dir: str | Path) -> ToolRegistry:
    """Build a :class:`ToolRegistry` with ``list_documents`` and ``read_document``.

    Both tools are async closures over ``(db, workspace_dir)``.
    """
    workspace = str(workspace_dir)
    reg = ToolRegistry()

    async def _list_documents() -> list[dict[str, str]]:
        return [
            {"id": row.id, "title": row.title, "kind": row.kind}
            for row in list_documents(db)
        ]

    async def _read_document(*, doc_id: str) -> dict[str, Any]:
        row = get_document(db, doc_id)
        if row is None:
            return {"error": "document not found"}
        text = extract_text(os.path.join(workspace, row.path), row.kind)
        return {"title": row.title, "kind": row.kind, "text": text}

    reg.register(
        ToolSpec(
            name="list_documents",
            description="List all ingested documents with their id, title and kind.",
            parameters={"type": "object", "properties": {}},
        ),
        _list_documents,
    )
    reg.register(
        ToolSpec(
            name="read_document",
            description="Read the full text of a document by its id.",
            parameters={
                "type": "object",
                "properties": {"doc_id": {"type": "string"}},
                "required": ["doc_id"],
            },
        ),
        _read_document,
    )
    return reg
