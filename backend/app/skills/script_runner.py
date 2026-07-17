"""Deterministic executor for ``kind="script"`` skills (ADR-0014).

A script skill is pure Python source that transforms a document's text into a
result string **without** an agent loop and **without** any LLM call at
runtime — the same input always yields the same output. This module provides
two cooperating pieces:

- :func:`validate_script` — static, fail-closed AST analysis run at *build*
  time (inside ``_validate_config``). It rejects syntax errors and any AST
  node that could escape the sandbox: ``import``/``__import__``, attribute
  access on dunder names (``__builtins__``, ``__globals__`` …), and calls to
  the usual footguns (``eval``/``exec``/``compile``/``open``/``breakpoint``).
- :func:`run_script` — runtime execution in a restricted namespace: a tiny
  allow-list of builtins, a curated set of safe stdlib modules, and a wall-clock
  timeout. The script receives the document text in
  ``document`` (alias ``input_text``) and returns its result either by
  ``return``-ing a string from a ``main()`` function, by assigning a global
  ``result`` variable, or via captured ``print`` output.

This is deliberately a *process-local* sandbox (option (a) of the plan's
sandbox decision): simple and dependency-free, with defence in depth (AST
gate + restricted globals + wall-clock timeout). A memory cap is intentionally
NOT applied in-process: ``RLIMIT_AS`` would constrain the whole host process
(run_script executes on the event-loop thread); memory isolation is deferred to
the hardened subprocess executor tracked as future work in ADR-0014.
"""

from __future__ import annotations

import ast
import signal
from typing import Any

# Builtins available to script skills. Anything that touches the outside
# world (open files, import, exec, network via ``__import__``) is omitted.
_SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "ascii": ascii,
    "bin": bin,
    "bool": bool,
    "bytearray": bytearray,
    "bytes": bytes,
    "callable": callable,
    "chr": chr,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "format": format,
    "frozenset": frozenset,
    # NOTE: getattr/hasattr/setattr are intentionally EXCLUDED. They take an
    # attribute name as a *string*, which the AST dunder guard cannot see
    # (it inspects ast.Attribute, not ast.Constant). Allowing them re-opens the
    # classic escape `getattr(object, "__subclasses__")()`. See validate_script.
    "hash": hash,
    "hex": hex,
    "int": int,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "iter": iter,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "object": object,
    "oct": oct,
    "ord": ord,
    "pow": pow,
    "print": print,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    # NOTE: `type` stays usable for isinstance/issubclass and plain
    # construction; dunder attribute access on it is blocked by validate_script
    # (e.g. `type(x).__subclasses__` is rejected as dunder access).
    "type": type,
    "zip": zip,
    "True": True,
    "False": False,
    "None": None,
}

# Modules a script may ``import`` (resolved by run_script into the namespace).
# Network, filesystem, subprocess and introspection modules are excluded.
_SAFE_MODULES: dict[str, Any] = {}

try:  # pragma: no cover - import side effects only
    import json as _json

    _SAFE_MODULES["json"] = _json
except ImportError:  # pragma: no cover
    pass
try:  # pragma: no cover
    import re as _re

    _SAFE_MODULES["re"] = _re
except ImportError:  # pragma: no cover
    pass
try:  # pragma: no cover
    import math as _math

    _SAFE_MODULES["math"] = _math
except ImportError:  # pragma: no cover
    pass
try:  # pragma: no cover
    import statistics as _statistics

    _SAFE_MODULES["statistics"] = _statistics
except ImportError:  # pragma: no cover
    pass
try:  # pragma: no cover
    import collections as _collections

    _SAFE_MODULES["collections"] = _collections
except ImportError:  # pragma: no cover
    pass

# Names that must never be reachable, used by the AST checker. The dynamic
# attribute helpers (getattr/hasattr/setattr/delattr) take an attribute name as
# a string, which the dunder guard cannot inspect — so they are fail-closed
# forbidden even though they are also omitted from _SAFE_BUILTINS.
_FORBIDDEN_BUILTINS = {
    "__import__",
    "eval",
    "exec",
    "compile",
    "open",
    "breakpoint",
    "globals",
    "locals",
    "vars",
    "input",
    "memoryview",
    "exit",
    "quit",
    "getattr",
    "hasattr",
    "setattr",
    "delattr",
}

# Default per-run limits.
DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_MEMORY_BYTES = 256 * 1024 * 1024  # 256 MiB


class ScriptValidationError(ValueError):
    """Raised when a script fails static (build-time) validation."""


class ScriptRuntimeError(RuntimeError):
    """Raised when a script fails at runtime (timeout, error, bad output)."""


# --------------------------------------------------------------------------- #
# Static validation (build time)
# --------------------------------------------------------------------------- #


def _forbidden_name(node: ast.AST) -> str | None:
    """Return a human reason if ``node`` touches a forbidden name, else None."""
    # Direct import statements are never allowed (modules come from the
    # pre-resolved _SAFE_MODULES namespace, not via the import machinery).
    if isinstance(node, ast.Import):
        return "import statements are not allowed"
    if isinstance(node, ast.ImportFrom):
        return "from-import statements are not allowed"
    if isinstance(node, ast.Attribute):
        if node.attr.startswith("__") and node.attr.endswith("__"):
            return f"dunder attribute access is not allowed: {node.attr!r}"
    if isinstance(node, ast.Name):
        if node.id in _FORBIDDEN_BUILTINS:
            return f"forbidden builtin: {node.id!r}"
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id in _FORBIDDEN_BUILTINS:
            return f"forbidden call: {func.id!r}"
        if isinstance(func, ast.Attribute) and func.attr in _FORBIDDEN_BUILTINS:
            return f"forbidden call: .{func.attr!r}"
    return None


def validate_script(code: str) -> None:
    """Statically validate ``code``; raise :class:`ScriptValidationError` on issues.

    Checks (fail-closed):

    - non-empty source;
    - syntactically valid Python (``ast.parse``);
    - no ``import`` / ``from-import`` statements;
    - no dunder attribute access (``__builtins__``, ``__subclasses__``, …);
    - no reference to forbidden builtins (``eval``/``exec``/``open``/…).
    """
    if not code or not code.strip():
        raise ScriptValidationError("script code is empty")

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ScriptValidationError(f"script has invalid syntax: {exc.msg}") from exc

    for node in ast.walk(tree):
        reason = _forbidden_name(node)
        if reason is not None:
            raise ScriptValidationError(reason)


# --------------------------------------------------------------------------- #
# Runtime execution
# --------------------------------------------------------------------------- #


class _ScriptTimeoutError(Exception):
    """Internal sentinel raised by the SIGALRM handler."""


def _timeout_handler(signum: int, frame: Any) -> None:  # noqa: ARG001
    raise _ScriptTimeoutError("script exceeded the time limit")


def _build_globals(document: str) -> dict[str, Any]:
    """Build the restricted globals namespace for a script run."""
    captured: list[str] = []

    def _capture_print(*args: Any, **kwargs: Any) -> None:
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        captured.append(sep.join(str(a) for a in args) + end)

    builtins = dict(_SAFE_BUILTINS)
    builtins["print"] = _capture_print

    namespace: dict[str, Any] = {
        "__builtins__": builtins,
        # Pre-resolved safe modules (no import machinery needed).
        **_SAFE_MODULES,
        # Input contract.
        "document": document,
        "input_text": document,
        # Output sink inspected after execution.
        "result": None,
        "_captured": captured,
    }
    return namespace


def _extract_result(namespace: dict[str, Any]) -> str:
    """Determine the script's output string from its post-run namespace."""
    # 1. An explicit ``result`` global wins.
    result = namespace.get("result")
    if isinstance(result, str):
        return result
    if result is not None:
        return str(result)
    # 2. A ``main()`` function that returns a string.
    main = namespace.get("main")
    if callable(main):
        out = main()
        if isinstance(out, str):
            return out
        if out is not None:
            return str(out)
    # 3. Captured print output (strip a single trailing newline for ergonomics).
    captured: list[str] = namespace.get("_captured", [])
    if captured:
        text = "".join(captured)
        return text[:-1] if text.endswith("\n") else text
    return ""


def run_script(
    code: str,
    doc_text: str,
    params: dict | None = None,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    memory_bytes: int = DEFAULT_MEMORY_BYTES,
) -> str:
    """Execute a validated script over ``doc_text`` and return its result string.

    The script is run synchronously in the current process inside a restricted
    namespace (see module docstring). A wall-clock ``timeout_seconds`` bounds
    runaway scripts. ``memory_bytes`` is accepted for API stability but is a
    no-op in-process (memory isolation is deferred to the subprocess executor,
    see ADR-0014).

    Raises :class:`ScriptRuntimeError` on timeout, memory overrun, or any
    exception raised by the script itself.
    """
    # Re-validate defensively: callers should have validated at build time, but
    # a committed script is only as trustworthy as its last validation.
    validate_script(code)

    namespace = _build_globals(doc_text)
    if params:
        namespace["params"] = params

    # NOTE: no in-process memory cap. RLIMIT_AS would apply to the *whole* host
    # process (run_script runs in the main event-loop thread), causing spurious
    # MemoryError in unrelated server code and a risk of crashing the host.
    # Memory isolation is deferred to the hardened subprocess executor tracked
    # in ADR-0014; for now a runaway script is bounded by the wall-clock timeout
    # below. `memory_bytes` is accepted for API stability but is a no-op here.
    del memory_bytes

    old_handler = signal.getsignal(signal.SIGALRM)
    # signal.setitimer accepts fractional seconds (signal.alarm is int-only).
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    signal.signal(signal.SIGALRM, _timeout_handler)
    try:
        exec(compile(code, "<script-skill>", "exec"), namespace)  # noqa: S102
    except _ScriptTimeoutError as exc:
        raise ScriptRuntimeError(
            f"script exceeded the {timeout_seconds}s time limit"
        ) from exc
    except MemoryError as exc:
        # Unlikely now that we don't set RLIMIT_AS, but surface it deterministically.
        raise ScriptRuntimeError("script exceeded the memory limit") from exc
    except Exception as exc:  # noqa: BLE001 — surface any script error verbatim
        raise ScriptRuntimeError(f"script raised: {exc}") from exc
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)

    return _extract_result(namespace)


async def run_script_async(
    code: str,
    doc_text: str,
    params: dict | None = None,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    memory_bytes: int = DEFAULT_MEMORY_BYTES,
) -> str:
    """Async wrapper around :func:`run_script` for the apply path.

    Runs synchronously in the event-loop (main) thread rather than via
    ``run_in_executor`` because the SIGALRM-based wall-clock timeout requires
    the main thread (``signal.setitimer`` raises ``ValueError`` in a worker
    thread). A hanging script is bounded by ``timeout_seconds`` (default 5s),
    so the event loop is blocked for at most that long. A hardened subprocess
    isolation that removes this constraint is tracked as future work in
    ADR-0014.
    """
    return run_script(
        code,
        doc_text,
        params,
        timeout_seconds=timeout_seconds,
        memory_bytes=memory_bytes,
    )
