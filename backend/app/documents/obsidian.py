from __future__ import annotations

import re
from pathlib import Path

from app.storage.db import Database
from app.storage.repo_document import list_documents

_WIKI_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def build_title_to_stem_map(db: Database) -> dict[str, str]:
    mapping: dict[str, str] = {}
    ambiguous: set[str] = set()
    for doc in list_documents(db):
        if not doc.title or not doc.path:
            continue
        if doc.title in ambiguous:
            continue
        stem = Path(doc.path).stem
        existing = mapping.get(doc.title)
        if existing is None:
            mapping[doc.title] = stem
        elif existing != stem:
            del mapping[doc.title]
            ambiguous.add(doc.title)
    return mapping


def rewrite_wiki_links(text: str, mapping: dict[str, str]) -> str:
    if not text or not mapping:
        return text

    def _replace(match: re.Match[str]) -> str:
        inner = match.group(1)
        alias_sep = inner.find("|")
        if alias_sep >= 0:
            target = inner[:alias_sep]
            suffix = inner[alias_sep:]
        else:
            target = inner
            suffix = ""

        heading_sep = target.find("#")
        if heading_sep >= 0:
            file_part = target[:heading_sep]
            heading = target[heading_sep:]
        else:
            file_part = target
            heading = ""

        stem = mapping.get(file_part)
        if stem is None:
            return match.group(0)
        return f"[[{stem}{heading}{suffix}]]"

    return _WIKI_LINK_RE.sub(_replace, text)
