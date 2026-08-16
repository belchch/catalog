from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

import docx
from docx.oxml.ns import qn

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?\n)---[ \t]*(?:\n|\Z)", re.DOTALL)
_WIKI_RE = re.compile(r"(?<!!)\[\[([^\]]+)\]\]")
_HR_RE = re.compile(r"-{3,}")
_UL_RE = re.compile(r"^[ \t]*[-*+][ \t]+(.*)$")
_OL_RE = re.compile(r"^[ \t]*\d{1,9}[.)][ \t]+(.*)$")
_SEP_CELL_RE = re.compile(r":?-{3,}:?")
_LINKS_HEADING = "Ссылки"
_LINKS_EXPORT_HEADING = "Источники"
_MONO_FONT = "Courier New"


def render_docx(md: str, *, template: Path | None = None) -> bytes:
    document = _open_document(template)
    body, props = _split_frontmatter(md or "")
    if props.get("title"):
        document.core_properties.title = props["title"]
    if props.get("author"):
        document.core_properties.author = props["author"]
    _render_blocks(document, _rewrite_wikilinks(body))
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _open_document(template: Path | None) -> docx.Document:
    if template is None:
        return docx.Document()
    document = docx.Document(str(template))
    body = document.element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)
    return document


def _split_frontmatter(text: str) -> tuple[str, dict[str, str]]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("\ufeff"):
        text = text[1:]
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return text, {}
    props: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip().strip("\"'")
        if key in ("title", "author") and value:
            props[key] = value
    return text[match.end() :], props


def _rewrite_wikilinks(text: str) -> str:
    parts: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        fence = text.find("```", index)
        if fence == -1:
            parts.append(_WIKI_RE.sub(_wikilink_replace, text[index:]))
            break
        parts.append(_WIKI_RE.sub(_wikilink_replace, text[index:fence]))
        closing = text.find("```", fence + 3)
        if closing == -1:
            parts.append(text[fence:])
            break
        parts.append(text[fence : closing + 3])
        index = closing + 3
    return "".join(parts)


def _wikilink_replace(match: re.Match[str]) -> str:
    inner = match.group(1)
    alias_sep = inner.find("|")
    if alias_sep >= 0:
        return inner[alias_sep + 1 :].strip()
    target = inner
    heading_sep = target.find("#")
    if heading_sep >= 0:
        target = target[:heading_sep]
    return target.strip()


def _render_blocks(document: docx.Document, text: str) -> None:
    lines = text.split("\n")
    index = 0
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        _add_paragraph(document, " ".join(line.strip() for line in paragraph_lines))
        paragraph_lines.clear()

    while index < len(lines):
        line = lines[index]
        if line.strip() == "":
            flush_paragraph()
            index += 1
            continue
        if line.startswith("```"):
            flush_paragraph()
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and not lines[index].startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            _add_code(document, "\n".join(code_lines).rstrip("\n"))
            continue
        heading = _parse_heading(line)
        if heading is not None:
            flush_paragraph()
            level, heading_text = heading
            if heading_text == _LINKS_HEADING:
                heading_text = _LINKS_EXPORT_HEADING
            _add_heading(document, level, heading_text)
            index += 1
            continue
        if _HR_RE.fullmatch(line.strip()):
            flush_paragraph()
            document.add_page_break()
            index += 1
            continue
        stripped = line.lstrip()
        if stripped.startswith("|") and "|" in stripped[1:]:
            flush_paragraph()
            rows: list[list[str]] = []
            while index < len(lines):
                candidate = lines[index].lstrip()
                if not (candidate.startswith("|") and "|" in candidate[1:]):
                    break
                rows.append(_split_table_row(candidate))
                index += 1
            if len(rows) >= 2 and _is_separator_row(rows[1]):
                del rows[1]
            if rows:
                _add_table(document, rows)
            continue
        unordered = _UL_RE.match(line)
        if unordered is not None:
            flush_paragraph()
            while index < len(lines):
                item = _UL_RE.match(lines[index])
                if item is None:
                    break
                _add_list_item(document, item.group(1), ordered=False)
                index += 1
            continue
        ordered = _OL_RE.match(line)
        if ordered is not None:
            flush_paragraph()
            while index < len(lines):
                item = _OL_RE.match(lines[index])
                if item is None:
                    break
                _add_list_item(document, item.group(1), ordered=True)
                index += 1
            continue
        paragraph_lines.append(line)
        index += 1
    flush_paragraph()


def _parse_heading(line: str) -> tuple[int, str] | None:
    if not line.startswith("#"):
        return None
    level = 0
    while level < len(line) and level < 6 and line[level] == "#":
        level += 1
    if level < len(line) and line[level] not in " \t":
        return None
    text = line[level:].strip()
    if text.endswith("#"):
        text = text.rstrip("#").rstrip()
    return level, text


def _split_table_row(line: str) -> list[str]:
    raw = line.strip()
    if raw.startswith("|"):
        raw = raw[1:]
    if raw.endswith("|") and not raw.endswith("\\|"):
        raw = raw[:-1]
    cells: list[str] = []
    current: list[str] = []
    index = 0
    while index < len(raw):
        if raw[index] == "\\" and index + 1 < len(raw) and raw[index + 1] == "|":
            current.append("|")
            index += 2
            continue
        if raw[index] == "|":
            cells.append("".join(current).strip())
            current = []
            index += 1
            continue
        current.append(raw[index])
        index += 1
    cells.append("".join(current).strip())
    return cells


def _is_separator_row(cells: list[str]) -> bool:
    if not cells:
        return False
    return all(_SEP_CELL_RE.fullmatch(cell.replace(" ", "")) is not None for cell in cells)


def _add_heading(document: docx.Document, level: int, text: str) -> None:
    try:
        paragraph = document.add_heading("", level=level)
    except ValueError:
        paragraph = document.add_paragraph()
    _add_runs(paragraph, text)


def _add_paragraph(document: docx.Document, text: str) -> None:
    paragraph = document.add_paragraph()
    _add_runs(paragraph, text)


def _add_list_item(document: docx.Document, text: str, *, ordered: bool) -> None:
    style = "List Number" if ordered else "List Bullet"
    try:
        paragraph = document.add_paragraph("", style=style)
    except ValueError:
        paragraph = document.add_paragraph()
    _add_runs(paragraph, text)


def _add_code(document: docx.Document, text: str) -> None:
    if text == "":
        paragraph = document.add_paragraph()
        _apply_monospace(paragraph.add_run(""))
        return
    for line in text.split("\n"):
        paragraph = document.add_paragraph()
        _apply_monospace(paragraph.add_run(line))


def _add_table(document: docx.Document, rows: list[list[str]]) -> None:
    width = max(len(row) for row in rows)
    if width == 0:
        return
    try:
        table = document.add_table(rows=len(rows), cols=width, style="Table Grid")
    except ValueError:
        table = document.add_table(rows=len(rows), cols=width)
    for row_index, row in enumerate(rows):
        for col_index in range(width):
            value = row[col_index] if col_index < len(row) else ""
            cell = table.cell(row_index, col_index)
            cell.text = ""
            _add_runs(cell.paragraphs[0], value)


def _add_runs(paragraph: object, text: str) -> None:
    for chunk, bold, italic, code in _iter_inlines(text):
        run = paragraph.add_run(chunk)
        if bold:
            run.bold = True
        if italic:
            run.italic = True
        if code:
            _apply_monospace(run)


def _apply_monospace(run: object) -> None:
    run.font.name = _MONO_FONT
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.get_or_add_rFonts()
    r_fonts.set(qn("w:ascii"), _MONO_FONT)
    r_fonts.set(qn("w:hAnsi"), _MONO_FONT)
    r_fonts.set(qn("w:eastAsia"), _MONO_FONT)
    r_fonts.set(qn("w:cs"), _MONO_FONT)


def _iter_inlines(text: str) -> list[tuple[str, bool, bool, bool]]:
    runs: list[tuple[str, bool, bool, bool]] = []
    buffer: list[str] = []
    index = 0
    length = len(text)

    def flush() -> None:
        if buffer:
            runs.append(("".join(buffer), False, False, False))
            buffer.clear()

    while index < length:
        if text[index] == "`":
            closing = text.find("`", index + 1)
            if closing != -1:
                flush()
                runs.append((text[index + 1 : closing], False, False, True))
                index = closing + 1
                continue
        if text.startswith("**", index):
            closing = text.find("**", index + 2)
            if closing != -1:
                flush()
                for chunk, _bold, italic, code in _iter_inlines(text[index + 2 : closing]):
                    runs.append((chunk, not code, italic, code))
                index = closing + 2
                continue
        if text[index] == "*":
            closing = index + 1
            while closing < length:
                if text[closing] == "*" and not text.startswith("**", closing):
                    break
                closing += 1
            if closing < length and text[closing] == "*":
                flush()
                for chunk, bold, _italic, code in _iter_inlines(text[index + 1 : closing]):
                    runs.append((chunk, bold, not code, code))
                index = closing + 1
                continue
        buffer.append(text[index])
        index += 1
    flush()
    return runs
