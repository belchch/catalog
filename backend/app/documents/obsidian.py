from __future__ import annotations

import re
from pathlib import Path

from app.storage.db import Database
from app.storage.repo_document import list_documents

_WIKI_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_LINKS_HEADING = "## Ссылки"
_TRAILING_LINKS_SECTION_RE = re.compile(
    r"(?:\n{2,}|\A)## Ссылки\n[\s\S]*\Z"
)
_TRAILING_SOURCE_MULTI_RE = re.compile(
    r"(?:\n{2,}|\A)Источники:\n(?:- \[\[[^\]]+\]\]\n?)+\Z"
)
_TRAILING_SOURCE_SINGLE_RE = re.compile(
    r"(?:\n{2,}|\A)Источник: \[\[[^\]]+\]\]\n?\Z"
)


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


def _unique_stems(parent_stems: list[str]) -> list[str]:
    seen: set[str] = set()
    stems: list[str] = []
    for stem in parent_stems:
        if not stem or stem in seen:
            continue
        seen.add(stem)
        stems.append(stem)
    return stems


def _format_links_section(stems: list[str]) -> str:
    lines = [_LINKS_HEADING, ""]
    lines.extend(f"- [[{stem}]]" for stem in stems)
    return "\n".join(lines) + "\n"


def _strip_trailing_links_blocks(text: str) -> str:
    body = text
    while True:
        matched = False
        for pattern in (
            _TRAILING_LINKS_SECTION_RE,
            _TRAILING_SOURCE_MULTI_RE,
            _TRAILING_SOURCE_SINGLE_RE,
        ):
            match = pattern.search(body)
            if match is not None:
                body = body[: match.start()]
                matched = True
                break
        if not matched:
            break
    return body


def ensure_parent_wikilinks(text: str, parent_stems: list[str]) -> str:
    body = text or ""
    stems = _unique_stems(parent_stems)
    if not stems:
        return body

    body = _strip_trailing_links_blocks(body)
    section = _format_links_section(stems)
    base = body.rstrip()
    if base:
        return f"{base}\n\n{section}"
    return section
