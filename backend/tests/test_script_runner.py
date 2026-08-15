"""Tests for the deterministic script sandbox (ADR-0014).

Covers three layers:

- **Static validation** (``validate_script``): empty/syntax/forbidden imports/
  dangerous builtins/dunder access are rejected; clean code passes.
- **Runtime execution** (``run_script``): a clean function returns the expected
  text via each of the three output conventions (``main()``, ``result``,
  ``print``); safe modules (``json``, ``re``) are usable.
- **Timeout**: an infinite loop is killed by the wall-clock limit.
"""

from __future__ import annotations

import pytest

from catalog.api.sessions import PLANNER_SYSTEM_PROMPT
from catalog.api.skills import BUILD_SKILL_SYSTEM_PROMPT, _BUILD_SKILL_PARAMETERS
from catalog.skills.script_runner import (
    SCRIPT_CODE_CONTRACT_EN,
    SCRIPT_CODE_CONTRACT_RU,
    ScriptRuntimeError,
    ScriptValidationError,
    run_script,
    validate_script,
)

# A generous memory ceiling for tests so RLIMIT_AS never interferes with the
# test process's own address space (the default 256 MiB can be too low on
# macOS where the interpreter maps far more virtual memory).
_TEST_MEM = 8 * 1024 * 1024 * 1024  # 8 GiB


# --------------------------------------------------------------------------- #
# Static validation
# --------------------------------------------------------------------------- #


def test_validate_rejects_empty() -> None:
    with pytest.raises(ScriptValidationError, match="empty"):
        validate_script("")
    with pytest.raises(ScriptValidationError, match="empty"):
        validate_script("   \n  ")


def test_validate_rejects_syntax_error() -> None:
    with pytest.raises(ScriptValidationError, match="syntax"):
        validate_script("def broken(:\n")


def test_validate_rejects_import() -> None:
    with pytest.raises(ScriptValidationError, match="import"):
        validate_script("import os\nresult = 'x'")
    with pytest.raises(ScriptValidationError, match="import"):
        validate_script("from os import path\nresult = 'x'")


def test_validate_rejects_dangerous_builtins() -> None:
    for name in ("eval", "exec", "open", "compile", "__import__"):
        with pytest.raises(ScriptValidationError):
            validate_script(f"x = {name}('1')\nresult = 'x'")


def test_validate_rejects_dunder_attribute_access() -> None:
    with pytest.raises(ScriptValidationError, match="dunder"):
        validate_script("result = ''.__class__.__bases__")


def test_validate_rejects_dynamic_attribute_helpers() -> None:
    """getattr/hasattr/setattr/delattr take a string attribute name and bypass
    the AST dunder guard — they must be rejected (sandbox-escape vectors)."""
    for code in (
        "result = getattr(object, '__subclasses__')()",
        "result = hasattr(object, '__subclasses__')",
        "setattr(result, 'x', 1)",
        "delattr(object, 'x')",
    ):
        with pytest.raises(ScriptValidationError):
            validate_script(code)


def test_validate_rejects_getattr_subclass_escape() -> None:
    """The textbook CPython sandbox escape via getattr must be blocked."""
    with pytest.raises(ScriptValidationError):
        validate_script(
            "cls = getattr(object, '__subclasses__')()[0]\n"
            "result = cls.__name__\n"
        )


def test_validate_accepts_clean_code() -> None:
    validate_script("result = document.upper()")
    validate_script(
        "def main():\n"
        "    lines = document.split('\\n')\n"
        "    return str(len(lines))\n"
    )


# --------------------------------------------------------------------------- #
# Runtime execution
# --------------------------------------------------------------------------- #


def test_run_script_result_via_main() -> None:
    code = "def main():\n    return document.upper()\n"
    out = run_script(code, "hello world", memory_bytes=_TEST_MEM)
    assert out == "HELLO WORLD"


def test_run_script_main_documents() -> None:
    code = "def main(documents):\n    return '\\n'.join(d.upper() for d in documents)\n"
    out = run_script(
        code, "hello", documents=["hello", "world"], memory_bytes=_TEST_MEM
    )
    assert out == "HELLO\nWORLD"


def test_run_script_main_document_arg() -> None:
    code = "def main(document):\n    return document[::-1]\n"
    out = run_script(code, "abc", memory_bytes=_TEST_MEM)
    assert out == "cba"


def test_run_script_documents_global_defaults_to_single() -> None:
    code = "result = str(len(documents)) + ':' + documents[0]\n"
    out = run_script(code, "solo", memory_bytes=_TEST_MEM)
    assert out == "1:solo"


def test_run_script_result_via_global() -> None:
    code = "result = document.replace('a', 'A')\n"
    out = run_script(code, "banana", memory_bytes=_TEST_MEM)
    assert out == "bAnAnA"


def test_run_script_result_list_of_strings() -> None:
    code = "result = [document, document.upper()]\n"
    out = run_script(code, "hello", memory_bytes=_TEST_MEM)
    assert out == ["hello", "HELLO"]


def test_run_script_main_returns_list_of_strings() -> None:
    code = "def main(document):\n    return [document, 'x']\n"
    out = run_script(code, "ab", memory_bytes=_TEST_MEM)
    assert out == ["ab", "x"]


def test_run_script_result_via_print() -> None:
    code = "print(document[::-1])\n"
    out = run_script(code, "abc", memory_bytes=_TEST_MEM)
    assert out == "cba"


def test_run_script_uses_safe_modules() -> None:
    # json + re are in the safe-module allow-list.
    code = (
        "data = json.loads(document)\n"
        "result = str(sorted(data.keys()))\n"
    )
    out = run_script(code, '{"b": 1, "a": 2}', memory_bytes=_TEST_MEM)
    assert "a" in out and "b" in out

    code2 = "result = re.sub(r'\\d+', '#', document)\n"
    out2 = run_script(code2, "abc123def456", memory_bytes=_TEST_MEM)
    assert out2 == "abc#def#"


def test_script_code_contract_lists_preinjected_modules() -> None:
    for name in ("collections", "json", "math", "re", "statistics"):
        assert name in SCRIPT_CODE_CONTRACT_RU
        assert name in SCRIPT_CODE_CONTRACT_EN
    assert "import/from-import запрещены" in SCRIPT_CODE_CONTRACT_RU
    assert "import/from-import are forbidden" in SCRIPT_CODE_CONTRACT_EN
    assert SCRIPT_CODE_CONTRACT_RU in BUILD_SKILL_SYSTEM_PROMPT
    assert SCRIPT_CODE_CONTRACT_RU in PLANNER_SYSTEM_PROMPT
    assert (
        SCRIPT_CODE_CONTRACT_EN
        in _BUILD_SKILL_PARAMETERS["properties"]["code"]["description"]
    )


def test_run_script_empty_output() -> None:
    """A script that produces no output returns an empty string."""
    out = run_script("x = 1 + 1\n", "irrelevant", memory_bytes=_TEST_MEM)
    assert out == ""


# --------------------------------------------------------------------------- #
# Timeout
# --------------------------------------------------------------------------- #


def test_run_script_timeout() -> None:
    """An infinite loop is killed by the wall-clock timeout."""
    code = "while True:\n    pass\n"
    with pytest.raises(ScriptRuntimeError, match="time limit"):
        run_script(code, "", timeout_seconds=0.3, memory_bytes=_TEST_MEM)
