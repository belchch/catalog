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
  timeout. The script receives input as ``document`` (aliases ``input_text``,
  ``doc_text``, ``text``; joined text) and ``documents`` (alias ``texts``;
  ``list[str]`` of each input). It returns its result by ``return`` from
  ``main()`` / ``main(document)`` / ``main(documents)``, by assigning a global
  ``result``, or via ``print``. Both the timeout and the error wrapping cover
  the ``main()`` call, not just module-level execution.

This is deliberately a *process-local* sandbox (option (a) of the plan's
sandbox decision): simple and dependency-free, with defence in depth (AST
gate + restricted globals + wall-clock timeout). A memory cap is intentionally
NOT applied in-process: ``RLIMIT_AS`` would constrain the whole host process
(run_script executes on the event-loop thread); memory isolation is deferred to
the hardened subprocess executor tracked as future work in ADR-0014.
"""

from __future__ import annotations

import ast
import inspect
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

_SAFE_MODULE_LIST = ", ".join(sorted(_SAFE_MODULES))

SCRIPT_CODE_CONTRACT_RU = (
    f"операторы import/from-import запрещены и не нужны: в namespace уже "
    f"доступны модули {_SAFE_MODULE_LIST} (пиши сразу json.loads, re.sub и т.п.); "
    f"без open/eval/exec; вход — текст документа (xlsx уже как markdown-таблицы), "
    f"pandas/openpyxl и бинарные файлы недоступны"
)

SCRIPT_CODE_CONTRACT_EN = (
    f"import/from-import are forbidden and unnecessary: {_SAFE_MODULE_LIST} "
    f"are pre-injected into the namespace (use json.loads, re.sub, etc. directly); "
    f"no open/eval/exec; input is document text (xlsx is already markdown tables); "
    f"no pandas/openpyxl or binary file access"
)

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


def _build_globals(
    document: str, documents: list[str] | None = None
) -> dict[str, Any]:
    """Build the restricted globals namespace for a script run."""
    captured: list[str] = []

    def _capture_print(*args: Any, **kwargs: Any) -> None:
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        captured.append(sep.join(str(a) for a in args) + end)

    builtins = dict(_SAFE_BUILTINS)
    builtins["print"] = _capture_print

    docs = list(documents) if documents is not None else [document]
    namespace: dict[str, Any] = {
        "__builtins__": builtins,
        # Pre-resolved safe modules (no import machinery needed).
        **_SAFE_MODULES,
        # Input contract.
        "document": document,
        "input_text": document,
        "documents": docs,
        # Output sink inspected after execution.
        "result": None,
        "_captured": captured,
    }
    return namespace


_LIST_PARAM_NAMES = ("documents", "texts")
_TEXT_PARAM_NAMES = ("document", "input_text", "doc_text", "text")
_INPUT_PARAM_LIST = ", ".join((*_TEXT_PARAM_NAMES, *_LIST_PARAM_NAMES))


def _call_main(main: Any, namespace: dict[str, Any]) -> Any:
    try:
        sig = inspect.signature(main)
    except (TypeError, ValueError):
        return main()

    kwargs: dict[str, Any] = {}
    unknown: list[str] = []
    for name, param in sig.parameters.items():
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        if name in _LIST_PARAM_NAMES:
            kwargs[name] = namespace["documents"]
        elif name in _TEXT_PARAM_NAMES:
            kwargs[name] = namespace["document"]
        elif param.default is inspect.Parameter.empty:
            unknown.append(name)

    if unknown:
        names = ", ".join(repr(name) for name in unknown)
        raise ScriptRuntimeError(
            f"main() has unsupported required parameter(s): {names}; "
            f"the input is passed as one of: {_INPUT_PARAM_LIST}"
        )

    bound = sig.bind(**kwargs)
    bound.apply_defaults()
    return main(*bound.args, **bound.kwargs)


def _as_str_list(value: Any) -> list[str] | None:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    return None


def _extract_result(namespace: dict[str, Any]) -> str | list[str]:
    result = namespace.get("result")
    as_list = _as_str_list(result)
    if as_list is not None:
        return as_list
    if isinstance(result, str):
        return result
    if result is not None:
        return str(result)
    main = namespace.get("main")
    if callable(main):
        out = _call_main(main, namespace)
        out_list = _as_str_list(out)
        if out_list is not None:
            return out_list
        if isinstance(out, str):
            return out
        if out is not None:
            return str(out)
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
    documents: list[str] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    memory_bytes: int = DEFAULT_MEMORY_BYTES,
) -> str | list[str]:
    """Execute a validated script over ``doc_text`` and return its result string.

    The script is run synchronously in the current process inside a restricted
    namespace (see module docstring). ``documents`` is the per-document list
    (defaults to ``[doc_text]``). A wall-clock ``timeout_seconds`` bounds
    runaway scripts. ``memory_bytes`` is accepted for API stability but is a
    no-op in-process (memory isolation is deferred to the subprocess executor,
    see ADR-0014).

    Raises :class:`ScriptRuntimeError` on timeout, memory overrun, or any
    exception raised by the script itself.
    """
    # Re-validate defensively: callers should have validated at build time, but
    # a committed script is only as trustworthy as its last validation.
    validate_script(code)

    docs = list(documents) if documents is not None else [doc_text]
    namespace = _build_globals(doc_text, docs)
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
        return _extract_result(namespace)
    except _ScriptTimeoutError as exc:
        raise ScriptRuntimeError(
            f"script exceeded the {timeout_seconds}s time limit"
        ) from exc
    except MemoryError as exc:
        # Unlikely now that we don't set RLIMIT_AS, but surface it deterministically.
        raise ScriptRuntimeError("script exceeded the memory limit") from exc
    except ScriptRuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface any script error verbatim
        raise ScriptRuntimeError(f"script raised: {exc}") from exc
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


async def run_script_async(
    code: str,
    doc_text: str,
    params: dict | None = None,
    *,
    documents: list[str] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    memory_bytes: int = DEFAULT_MEMORY_BYTES,
) -> str | list[str]:
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
        documents=documents,
        timeout_seconds=timeout_seconds,
        memory_bytes=memory_bytes,
    )
