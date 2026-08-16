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

from catalog.skills.config import VerifyCheck


@dataclass
class CheckOutcome:
    check: str
    params: dict
    passed: bool
    reason: str | None
    source: str
    skipped: bool = False

    def as_dict(self) -> dict:
        return {
            "check": self.check,
            "params": dict(self.params),
            "passed": self.passed,
            "reason": self.reason,
            "source": self.source,
            "skipped": self.skipped,
        }


@dataclass
class VerifyResult:
    """Outcome of running a list of checks over a text."""

    passed: bool
    failures: list[str] = field(default_factory=list)
    checks: list[CheckOutcome] = field(default_factory=list)

    def as_payload(self) -> dict:
        return {
            "passed": self.passed,
            "failures": list(self.failures),
            "checks": [item.as_dict() for item in self.checks],
        }


# (text, params) -> None if ok, otherwise a human-readable failure reason.
CheckFn = Callable[[str, dict], str | None]

_REGISTRY: dict[str, CheckFn] = {}


def register_check(check_id: str, fn: CheckFn) -> None:
    """Register a check implementation under ``check_id`` (overwrites)."""
    _REGISTRY[check_id] = fn


def registered_checks() -> list[str]:
    """Return the ids of all registered checks (for skill-build validation)."""
    return list(_REGISTRY.keys())


_REQUIRED_PARAMS: dict[str, tuple[str, ...]] = {
    "min_length": ("min",),
    "max_length": ("max",),
    "regex_matches": ("pattern",),
    "has_section": ("heading",),
    "has_field": ("key",),
}


def verify_checks_params_hint() -> str:
    parts = [
        f"{check_id} requires {', '.join(keys)}"
        for check_id, keys in _REQUIRED_PARAMS.items()
    ]
    return "Params: " + "; ".join(parts) + "."


def is_custom_check_id(check_id: str | None) -> bool:
    return bool(check_id) and (
        check_id == "custom" or check_id.startswith("custom:")
    )


def custom_check_ref_id(check_id: str, params: dict | None = None) -> str | None:
    if check_id.startswith("custom:"):
        cid = check_id.split(":", 1)[1].strip()
        return cid or None
    if check_id == "custom":
        raw = params.get("id") if isinstance(params, dict) else None
        if raw is None or raw == "":
            return None
        cid = str(raw).strip()
        return cid or None
    return None


def builtin_check_labels() -> dict[str, str]:
    return {
        "non_empty": "Не пустой",
        "min_length": "Минимальная длина",
        "max_length": "Максимальная длина",
        "regex_matches": "Совпадение с regex",
        "no_leftover_placeholders": "Без плейсхолдеров",
        "markdown_well_formed": "Корректный markdown",
        "has_section": "Есть раздел",
        "has_field": "Есть поле",
        "table_parses": "Таблица парсится",
    }


def validate_verify_check(
    check_id: str | None,
    params: dict | None = None,
    *,
    available_checks: list[str] | None = None,
) -> str | None:
    payload = params if isinstance(params, dict) else {}
    if is_custom_check_id(check_id):
        if custom_check_ref_id(check_id or "", payload) is None:
            return "custom check requires id"
        return None
    known = available_checks if available_checks is not None else registered_checks()
    if not check_id or check_id not in known:
        return f"unknown verify check: {check_id!r}"
    required = _REQUIRED_PARAMS.get(check_id, ())
    for key in required:
        value = payload.get(key)
        if value is None or value == "":
            return f"{check_id} requires param {key!r}"
    return None


def validate_verify_checks(
    checks: list,
    *,
    available_checks: list[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    for vc in checks:
        if isinstance(vc, dict):
            check_id = vc.get("check")
            raw_params = vc.get("params")
        else:
            check_id = getattr(vc, "check", None)
            raw_params = getattr(vc, "params", None)
        params = raw_params if isinstance(raw_params, dict) else {}
        error = validate_verify_check(
            check_id, params, available_checks=available_checks
        )
        if error:
            errors.append(error)
    return errors


def _outcome(
    check: VerifyCheck,
    *,
    passed: bool,
    reason: str | None,
    source: str,
    skipped: bool = False,
) -> CheckOutcome:
    return CheckOutcome(
        check=check.check,
        params=dict(check.params),
        passed=passed,
        reason=reason,
        source=source,
        skipped=skipped,
    )


def run_verify(text: str, checks: list[VerifyCheck]) -> VerifyResult:
    failures: list[str] = []
    outcomes: list[CheckOutcome] = []
    for c in checks:
        if is_custom_check_id(c.check):
            reason = f"custom check requires async verify: {c.check}"
            outcomes.append(
                _outcome(
                    c,
                    passed=False,
                    reason=reason,
                    source="custom",
                    skipped=True,
                )
            )
            failures.append(reason)
            continue
        fn = _REGISTRY.get(c.check)
        if fn is None:
            reason = f"unknown check: {c.check}"
            outcomes.append(
                _outcome(
                    c,
                    passed=False,
                    reason=reason,
                    source="builtin",
                    skipped=True,
                )
            )
            failures.append(reason)
            continue
        reason = fn(text, c.params)
        outcomes.append(
            _outcome(
                c,
                passed=reason is None,
                reason=reason,
                source="builtin",
            )
        )
        if reason is not None:
            failures.append(f"{c.check}: {reason}")
    return VerifyResult(passed=not failures, failures=failures, checks=outcomes)


def _judge_user_message(criterion: str, text: str) -> str:
    return (
        "Ты проверяешь результат работы скилла по одному критерию.\n"
        "Критерий (утверждение, которое должно быть верно):\n"
        f"{criterion}\n\n"
        "Результат для проверки:\n"
        f"{text}\n\n"
        "Ответь строго одной строкой: PASS или FAIL: <краткая причина>."
    )


def _parse_judge_answer(answer: str, label: str) -> str | None:
    stripped = answer.strip()
    upper = stripped.upper()
    if upper.startswith("PASS"):
        return None
    if upper.startswith("FAIL"):
        reason = stripped.split(":", 1)[1].strip() if ":" in stripped else stripped
        return f"custom:{label}: {reason or 'failed'}"
    preview = stripped[:120] if stripped else "(empty)"
    return f"custom:{label}: unexpected judge reply: {preview}"


async def run_custom_judge(
    text: str,
    criterion: str,
    *,
    provider,
    model: str,
    label: str = "preview",
) -> str | None:
    from catalog.llm.base import Message

    if not model:
        return f"custom:{label}: missing model"
    try:
        from catalog.skills.budget import charge_nested_skill_llm

        charge_nested_skill_llm()
        resp = await provider.complete(
            model,
            [Message(role="user", content=_judge_user_message(criterion, text))],
            None,
            0.0,
        )
        answer = resp.content or ""
    except Exception as exc:
        return f"custom:{label}: judge error: {exc}"
    return _parse_judge_answer(answer, label)


async def run_verify_async(
    text: str,
    checks: list[VerifyCheck],
    *,
    db=None,
    provider=None,
    model: str = "",
) -> VerifyResult:
    from catalog.storage.repo_custom_check import CustomCheckRow, get_custom_check

    det = [c for c in checks if not is_custom_check_id(c.check)]
    custom = [c for c in checks if is_custom_check_id(c.check)]
    resolve_failures: list[str] = []
    resolve_errors: list[str | None] = [None] * len(custom)
    resolved: list[CustomCheckRow | None] = [None] * len(custom)
    if custom:
        if db is None:
            resolve_failures.append("custom check requires workspace db")
        else:
            for i, c in enumerate(custom):
                cid = custom_check_ref_id(c.check, c.params)
                if not cid:
                    msg = "custom: missing check id"
                    resolve_failures.append(msg)
                    resolve_errors[i] = msg
                    continue
                row = get_custom_check(db, cid)
                if row is None:
                    msg = f"unknown custom check: {cid!r}"
                    resolve_failures.append(msg)
                    resolve_errors[i] = msg
                    continue
                if row.hidden:
                    msg = f"hidden custom check: {cid!r}"
                    resolve_failures.append(msg)
                    resolve_errors[i] = msg
                    continue
                resolved[i] = row
    base = run_verify(text, det)
    can_judge = (
        base.passed
        and not resolve_failures
        and any(row is not None for row in resolved)
        and provider is not None
    )
    judge_failures: list[str] = []
    custom_outcomes: list[CheckOutcome] = []
    for i, c in enumerate(custom):
        row = resolved[i]
        resolve_error = resolve_errors[i]
        if can_judge and row is not None:
            reason = await run_custom_judge(
                text,
                row.prompt,
                provider=provider,
                model=model,
                label=row.name,
            )
            if reason is not None:
                judge_failures.append(reason)
            custom_outcomes.append(
                _outcome(
                    c,
                    passed=reason is None,
                    reason=reason,
                    source="custom",
                )
            )
            continue
        if resolve_error is not None and base.passed:
            custom_outcomes.append(
                _outcome(
                    c,
                    passed=False,
                    reason=resolve_error,
                    source="custom",
                )
            )
            continue
        skip_reason = None
        if provider is None and base.passed and not resolve_failures:
            skip_reason = "custom check requires LLM provider"
        custom_outcomes.append(
            _outcome(
                c,
                passed=False,
                reason=skip_reason,
                source="custom",
                skipped=True,
            )
        )
    outcomes: list[CheckOutcome] = []
    det_iter = iter(base.checks)
    custom_iter = iter(custom_outcomes)
    for c in checks:
        if is_custom_check_id(c.check):
            outcomes.append(next(custom_iter))
        else:
            outcomes.append(next(det_iter))
    if not base.passed or resolve_failures:
        return VerifyResult(
            passed=False,
            failures=base.failures + resolve_failures,
            checks=outcomes,
        )
    if not any(row is not None for row in resolved):
        return VerifyResult(
            passed=base.passed, failures=base.failures, checks=outcomes
        )
    if provider is None:
        return VerifyResult(
            passed=False,
            failures=["custom check requires LLM provider"],
            checks=outcomes,
        )
    return VerifyResult(
        passed=not judge_failures, failures=judge_failures, checks=outcomes
    )


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
