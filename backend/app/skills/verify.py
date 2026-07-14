"""Deterministic verify checks (ADR-0007).

Each check is a pure function ``(text, params) -> str | None`` returning a
human-readable failure reason, or ``None`` when the text passes. Checks are
registered by id and referenced from ``SkillConfig.verify_checks``.

The registry is **fail-closed**: an unknown check id makes ``run_verify``
return ``VerifyResult(passed=False)`` so a misconfigured skill never silently
skips validation.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from app.skills.config import VerifyCheck


@dataclass
class VerifyResult:
    """Outcome of running a list of checks over a text."""

    passed: bool
    failures: list[str] = field(default_factory=list)


# (text, params) -> None if ok, otherwise a human-readable failure reason.
CheckFn = Callable[[str, dict], str | None]

_REGISTRY: dict[str, CheckFn] = {}


def register_check(check_id: str, fn: CheckFn) -> None:
    """Register a check implementation under ``check_id`` (overwrites)."""
    _REGISTRY[check_id] = fn


def run_verify(text: str, checks: list[VerifyCheck]) -> VerifyResult:
    """Run all ``checks`` over ``text``; fail-closed on unknown ids.

    ``checks`` items are :class:`~app.skills.config.VerifyCheck` objects
    exposing ``.check`` and ``.params``.
    """
    failures: list[str] = []
    for c in checks:
        fn = _REGISTRY.get(c.check)
        if fn is None:
            # Fail-closed: an unknown check id must never pass.
            return VerifyResult(passed=False, failures=[f"unknown check: {c.check}"])
        reason = fn(text, c.params)
        if reason is not None:
            failures.append(f"{c.check}: {reason}")
    return VerifyResult(passed=not failures, failures=failures)


# --------------------------------------------------------------------------- #
# Built-in checks
# --------------------------------------------------------------------------- #


def _check_non_empty(text: str, params: dict) -> str | None:
    if not text.strip():
        return "result is empty after trim"
    return None


def _measure(text: str, unit: str) -> int:
    if unit == "lines":
        # Count non-empty lines to avoid trailing-newline ambiguity.
        return sum(1 for line in text.splitlines() if line.strip())
    return len(text)


def _check_min_length(text: str, params: dict) -> str | None:
    unit = params.get("unit", "chars")
    length = _measure(text, unit)
    minimum = params.get("min")
    if minimum is not None and length < minimum:
        return f"length {length} {unit} < min {minimum}"
    return None


def _check_max_length(text: str, params: dict) -> str | None:
    unit = params.get("unit", "chars")
    length = _measure(text, unit)
    maximum = params.get("max")
    if maximum is not None and length > maximum:
        return f"length {length} {unit} > max {maximum}"
    return None


def _check_regex_matches(text: str, params: dict) -> str | None:
    pattern = params.get("pattern")
    if not pattern:
        return "missing param 'pattern'"
    if not re.search(pattern, text):
        return f"no match for pattern {pattern!r}"
    return None


def _check_no_leftover_placeholders(text: str, params: dict) -> str | None:
    hits: list[str] = []
    if re.search(r"\{[^}]*\}", text):
        hits.append("{...}")
    if re.search(r"<[^>]+>", text):
        hits.append("<...>")
    if "TODO" in text:
        hits.append("TODO")
    if hits:
        return f"leftover placeholders: {', '.join(hits)}"
    return None


def _check_markdown_well_formed(text: str, params: dict) -> str | None:
    """Minimal markdown sanity check (regex-based, no external parser).

    Validates: non-empty, ATX headings (``#``) are well-formed, and any
    pipe-table block has a separator row (dashes) as its second line. This is
    intentionally a lightweight heuristic sufficient for the first slice
    (ADR-0007).
    """
    if not text.strip():
        return "empty markdown"
    lines = text.splitlines()
    for line in lines:
        stripped = line.lstrip()
        # An ATX heading is 1-6 '#' followed by whitespace or EOL.
        if stripped.startswith("#"):
            m = re.match(r"#{1,6}(\s|$)", stripped)
            if m is None:
                return f"malformed heading: {line!r}"
    # Table blocks: the first row of each contiguous |-block (a line starting
    # with '|') must be followed by a valid separator row (dashes). This catches
    # both a separator that lacks dashes and the case where the would-be header
    # is followed by a non-table line (no '|' prefix) — previously missed
    # because the old check only fired when the second line itself began '|'.
    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        prev_is_table = i > 0 and lines[i - 1].strip().startswith("|")
        if prev_is_table:
            continue  # not the start of a new table block
        # Block start: the next line must be a valid separator.
        if i + 1 >= len(lines):
            return f"table at line {i + 1} has no separator row"
        sep = lines[i + 1].strip()
        if not (_TABLE_SEP_RE.match(sep) and "-" in sep):
            return f"table missing separator row after line {i + 1}"
    return None


def _check_has_section(text: str, params: dict) -> str | None:
    heading = params.get("heading")
    if not heading:
        return "missing param 'heading'"
    level = params.get("level")
    if level is not None:
        prefix = "#" * int(level)
        pattern = rf"^{re.escape(prefix)}\s+{re.escape(heading)}\b"
    else:
        # Any level (1-6) heading with this text.
        pattern = rf"^#{{1,6}}\s+{re.escape(heading)}\b"
    if not re.search(pattern, text, flags=re.MULTILINE):
        lvl = f" (level {level})" if level else ""
        return f"no section {heading!r}{lvl}"
    return None


def _check_has_field(text: str, params: dict) -> str | None:
    key = params.get("key")
    if not key:
        return "missing param 'key'"
    pattern = rf"^{re.escape(key)}:\s*.+"
    if not re.search(pattern, text, flags=re.MULTILINE):
        return f"no field {key!r}"
    return None


_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]*-\|?[\s:|-]*$")


def _parse_table(text: str) -> list[list[str]] | None:
    """Parse a markdown table into rows of cells, or ``None`` if absent/invalid.

    A valid table is a contiguous block of lines starting with ``|``, where
    the second line is a separator (dashes). Returns the data rows (excluding
    header and separator).
    """
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            block: list[str] = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            # Need at least header + separator.
            if len(block) < 2:
                continue
            sep = block[1]
            if not _TABLE_SEP_RE.match(sep) or "-" not in sep:
                continue
            rows: list[list[str]] = []
            for raw in block:
                cells = [c.strip() for c in raw.strip().strip("|").split("|")]
                rows.append(cells)
            # Drop header (0) and separator (1).
            return rows[2:]
        else:
            i += 1
    return None


def _check_table_parses(text: str, params: dict) -> str | None:
    rows = _parse_table(text)
    if rows is None:
        return "no parseable markdown table"
    # Default min_rows=1: a header+separator with zero data rows does not count
    # as a real table (verification-checks.md: "минимум 1 строка данных").
    min_rows = params.get("min_rows", 1)
    min_cols = params.get("min_cols")
    if len(rows) < min_rows:
        return f"{len(rows)} data rows < min_rows {min_rows}"
    if min_cols is not None:
        ncols = max((len(r) for r in rows), default=0)
        if ncols < min_cols:
            return f"{ncols} cols < min_cols {min_cols}"
    return None


# Register built-ins.
register_check("non_empty", _check_non_empty)
register_check("min_length", _check_min_length)
register_check("max_length", _check_max_length)
register_check("regex_matches", _check_regex_matches)
register_check("no_leftover_placeholders", _check_no_leftover_placeholders)
register_check("markdown_well_formed", _check_markdown_well_formed)
register_check("has_section", _check_has_section)
register_check("has_field", _check_has_field)
register_check("table_parses", _check_table_parses)
