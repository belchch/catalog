from __future__ import annotations

import docx


def extract_text(path: str, kind: str) -> str:
    """Return the plain text of a stored document.

    - ``md`` / ``result_md`` -> raw file contents (utf-8).
    - ``docx`` -> paragraphs joined with newlines via python-docx.
    """
    if kind in ("md", "result_md"):
        with open(path, encoding="utf-8") as f:
            return f.read()
    if kind == "docx":
        document = docx.Document(path)
        return "\n".join(p.text for p in document.paragraphs)
    raise ValueError(f"unsupported kind: {kind}")
