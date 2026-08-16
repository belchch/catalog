from __future__ import annotations

import asyncio

from catalog.api.skills import _validate_config
from catalog.llm.base import CompletionResult, Message
from catalog.skills.config import SkillConfig, VerifyCheck
from catalog.skills.verify import (
    CheckOutcome,
    VerifyResult,
    registered_checks,
    run_custom_judge,
    run_verify,
    run_verify_async,
    validate_verify_check,
    validate_verify_checks,
    verify_checks_params_hint,
)
from catalog.storage.db import Database
from catalog.storage.repo_custom_check import (
    create_custom_check,
    hide_custom_check,
)


def _vc(check: str, **params: object) -> VerifyCheck:
    return VerifyCheck(check=check, params=dict(params))


# --------------------------------------------------------------------------- #
# non_empty
# --------------------------------------------------------------------------- #


def test_non_empty_pass() -> None:
    assert run_verify("hello", [_vc("non_empty")]).passed is True


def test_non_empty_fail_blank() -> None:
    r = run_verify("   \n  ", [_vc("non_empty")])
    assert r.passed is False
    assert "empty" in r.failures[0]


def test_non_empty_fail_empty_string() -> None:
    assert run_verify("", [_vc("non_empty")]).passed is False


# --------------------------------------------------------------------------- #
# min_length / max_length
# --------------------------------------------------------------------------- #


def test_min_length_chars_pass() -> None:
    assert run_verify("hello world", [_vc("min_length", min=5)]).passed is True


def test_min_length_chars_fail() -> None:
    r = run_verify("hi", [_vc("min_length", min=5)])
    assert r.passed is False
    assert "5" in r.failures[0]


def test_max_length_chars_fail() -> None:
    r = run_verify("hello world", [_vc("max_length", max=5)])
    assert r.passed is False


def test_min_length_lines() -> None:
    text = "line1\nline2\nline3"
    assert run_verify(text, [_vc("min_length", min=3, unit="lines")]).passed is True
    r = run_verify(text, [_vc("min_length", min=4, unit="lines")])
    assert r.passed is False


def test_max_length_lines() -> None:
    text = "a\nb\nc"
    assert run_verify(text, [_vc("max_length", max=3, unit="lines")]).passed is True
    assert run_verify(text, [_vc("max_length", max=2, unit="lines")]).passed is False


# --------------------------------------------------------------------------- #
# regex_matches
# --------------------------------------------------------------------------- #


def test_regex_matches_pass() -> None:
    assert run_verify("hello world", [_vc("regex_matches", pattern=r"world")]).passed is True


def test_regex_matches_fail() -> None:
    r = run_verify("hello", [_vc("regex_matches", pattern=r"\d+")])
    assert r.passed is False


# --------------------------------------------------------------------------- #
# no_leftover_placeholders
# --------------------------------------------------------------------------- #


def test_no_leftover_placeholders_pass() -> None:
    assert run_verify("clean text", [_vc("no_leftover_placeholders")]).passed is True


def test_no_leftover_placeholders_braces() -> None:
    r = run_verify("hello {name}", [_vc("no_leftover_placeholders")])
    assert r.passed is False
    assert "{...}" in r.failures[0]


def test_no_leftover_placeholders_angle() -> None:
    assert run_verify("hello <name>", [_vc("no_leftover_placeholders")]).passed is False


def test_no_leftover_placeholders_todo() -> None:
    assert run_verify("TODO: fix", [_vc("no_leftover_placeholders")]).passed is False


# --------------------------------------------------------------------------- #
# markdown_well_formed
# --------------------------------------------------------------------------- #


def test_markdown_well_formed_pass() -> None:
    text = "# Title\n\nSome paragraph.\n\n## Section\n\nMore text."
    assert run_verify(text, [_vc("markdown_well_formed")]).passed is True


def test_markdown_well_formed_empty() -> None:
    assert run_verify("   ", [_vc("markdown_well_formed")]).passed is False


def test_markdown_well_formed_bad_heading() -> None:
    # 7 '#' is not a valid ATX heading.
    r = run_verify("####### too many", [_vc("markdown_well_formed")])
    assert r.passed is False
    assert "heading" in r.failures[0]


def test_markdown_well_formed_good_heading_levels() -> None:
    text = "# H1\n## H2\n### H3\n#### H4\n##### H5\n###### H6"
    assert run_verify(text, [_vc("markdown_well_formed")]).passed is True


def test_markdown_well_formed_table_missing_separator_nonpipe() -> None:
    # Header row starts with '|', but the second line is plain text (no '|' /
    # not a valid separator) -> fail. Previously this slipped through because
    # the check only fired when the second line itself began with '|'.
    text = "| Name | Age |\nName and age"
    r = run_verify(text, [_vc("markdown_well_formed")])
    assert r.passed is False
    assert "separator" in r.failures[0]


def test_markdown_well_formed_table_valid_separator_passes() -> None:
    text = "| Name | Age |\n|------|-----|\n| Alice | 30 |"
    assert run_verify(text, [_vc("markdown_well_formed")]).passed is True


# --------------------------------------------------------------------------- #
# has_section
# --------------------------------------------------------------------------- #


def test_has_section_pass() -> None:
    text = "# Intro\n\nText.\n\n## Тезисы\n\n- point"
    assert run_verify(text, [_vc("has_section", heading="Тезисы")]).passed is True


def test_has_section_fail_missing() -> None:
    r = run_verify("# Intro\nText.", [_vc("has_section", heading="Тезисы")])
    assert r.passed is False


def test_has_section_with_level_pass() -> None:
    text = "# Intro\n## Details\n### Details"
    assert run_verify(text, [_vc("has_section", heading="Details", level=2)]).passed is True


def test_has_section_with_level_fail_wrong_level() -> None:
    text = "# Intro\n### Details"
    # level=2 but only level=3 exists.
    r = run_verify(text, [_vc("has_section", heading="Details", level=2)])
    assert r.passed is False


# --------------------------------------------------------------------------- #
# has_field
# --------------------------------------------------------------------------- #


def test_has_field_pass() -> None:
    text = "Автор: Иванов\nДата: 2026-07-14"
    assert run_verify(text, [_vc("has_field", key="Автор")]).passed is True


def test_has_field_fail() -> None:
    r = run_verify("Нет полей", [_vc("has_field", key="Автор")])
    assert r.passed is False


def test_has_field_empty_value_fail() -> None:
    # "key:" with no value should fail (^key:\s*.+ requires at least one char).
    r = run_verify("Автор:", [_vc("has_field", key="Автор")])
    assert r.passed is False


# --------------------------------------------------------------------------- #
# table_parses
# --------------------------------------------------------------------------- #


def test_table_parses_pass() -> None:
    text = (
        "| Name | Age |\n"
        "|------|-----|\n"
        "| Alice | 30 |\n"
        "| Bob | 25 |"
    )
    assert run_verify(text, [_vc("table_parses")]).passed is True


def test_table_parses_no_table() -> None:
    r = run_verify("just text", [_vc("table_parses")])
    assert r.passed is False


def test_table_parses_min_rows_fail() -> None:
    text = "| Name |\n|------|\n| Alice |"
    r = run_verify(text, [_vc("table_parses", min_rows=2)])
    assert r.passed is False


def test_table_parses_min_rows_pass() -> None:
    text = "| Name |\n|------|\n| Alice |\n| Bob |"
    assert run_verify(text, [_vc("table_parses", min_rows=2)]).passed is True


def test_table_parses_min_cols_fail() -> None:
    text = "| Name |\n|------|\n| Alice |"
    r = run_verify(text, [_vc("table_parses", min_cols=2)])
    assert r.passed is False


def test_table_parses_default_requires_data_row() -> None:
    # Header + separator but zero data rows: default min_rows=1 -> fail
    # (verification-checks.md: "минимум 1 строка данных").
    text = "| Name |\n|------|"
    r = run_verify(text, [_vc("table_parses")])
    assert r.passed is False
    assert "min_rows" in r.failures[0]


def test_table_parses_default_one_data_row_passes() -> None:
    text = "| Name |\n|------|\n| Alice |"
    assert run_verify(text, [_vc("table_parses")]).passed is True


# --------------------------------------------------------------------------- #
# unknown check — fail-closed
# --------------------------------------------------------------------------- #


def test_unknown_check_fail_closed() -> None:
    r = run_verify("anything", [_vc("does_not_exist")])
    assert r.passed is False
    assert r.failures == ["unknown check: does_not_exist"]


def test_validate_verify_check_min_length_requires_min() -> None:
    assert validate_verify_check("min_length", {}) == "min_length requires param 'min'"
    assert validate_verify_check("min_length", {"min": 5}) is None


def test_validate_verify_check_max_length_requires_max() -> None:
    assert validate_verify_check("max_length", {}) == "max_length requires param 'max'"
    assert validate_verify_check("max_length", {"max": 10}) is None


def test_validate_verify_check_unknown() -> None:
    assert validate_verify_check("does_not_exist", {}) == (
        "unknown verify check: 'does_not_exist'"
    )


def test_validate_verify_checks_accepts_verify_check_objects() -> None:
    errors = validate_verify_checks(
        [
            VerifyCheck(check="min_length", params={}),
            VerifyCheck(check="non_empty"),
        ]
    )
    assert errors == ["min_length requires param 'min'"]


def test_verify_checks_params_hint_lists_required_keys() -> None:
    hint = verify_checks_params_hint()
    assert "min_length requires min" in hint
    assert "max_length requires max" in hint
    assert "regex_matches requires pattern" in hint
    assert "has_section requires heading" in hint
    assert "has_field requires key" in hint


def test_registered_checks_cover_required_param_ids() -> None:
    known = set(registered_checks())
    for check_id in (
        "min_length",
        "max_length",
        "regex_matches",
        "has_section",
        "has_field",
    ):
        assert check_id in known


def test_validate_config_rejects_min_length_without_min() -> None:
    config = SkillConfig(
        name="Len",
        description="x",
        system_prompt="do it",
        allowed_tools=["read_document"],
        model="test",
        verify_checks=[VerifyCheck(check="min_length", params={})],
    )
    errors = _validate_config(config, ["read_document"], registered_checks())
    assert any("min_length requires param 'min'" in e for e in errors)


def test_validate_config_accepts_min_length_with_min() -> None:
    config = SkillConfig(
        name="Len",
        description="x",
        system_prompt="do it",
        allowed_tools=["read_document"],
        model="test",
        verify_checks=[VerifyCheck(check="min_length", params={"min": 8})],
    )
    assert _validate_config(config, ["read_document"], registered_checks()) == []


# --------------------------------------------------------------------------- #
# run_verify combining multiple checks
# --------------------------------------------------------------------------- #


def test_run_verify_multiple_all_pass() -> None:
    text = "# Report\n\nАвтор: Иванов\n\n| Col |\n|-----|\n| val |"
    r = run_verify(
        text,
        [
            _vc("non_empty"),
            _vc("markdown_well_formed"),
            _vc("has_section", heading="Report"),
            _vc("has_field", key="Автор"),
            _vc("table_parses"),
        ],
    )
    assert r.passed is True
    assert r.failures == []
    assert [c.check for c in r.checks] == [
        "non_empty",
        "markdown_well_formed",
        "has_section",
        "has_field",
        "table_parses",
    ]
    assert all(isinstance(c, CheckOutcome) for c in r.checks)
    assert all(c.passed and not c.skipped and c.source == "builtin" for c in r.checks)


def test_run_verify_multiple_some_fail() -> None:
    text = "# Report\n\nSome text."
    r = run_verify(
        text,
        [
            _vc("non_empty"),
            _vc("has_field", key="Автор"),
            _vc("table_parses"),
        ],
    )
    assert r.passed is False
    assert len(r.failures) == 2
    assert any("has_field" in f for f in r.failures)
    assert any("table_parses" in f for f in r.failures)
    assert [c.check for c in r.checks] == ["non_empty", "has_field", "table_parses"]
    assert [c.passed for c in r.checks] == [True, False, False]
    assert [c.skipped for c in r.checks] == [False, False, False]
    assert [c.source for c in r.checks] == ["builtin", "builtin", "builtin"]
    assert r.checks[0].reason is None
    assert r.checks[1].reason is not None
    assert r.checks[1].params == {"key": "Автор"}
    assert r.as_payload()["checks"][2]["check"] == "table_parses"


def test_run_verify_empty_checks_passes() -> None:
    # No checks → vacuously passes.
    r = run_verify("anything", [])
    assert r.passed is True
    assert isinstance(r, VerifyResult)
    assert r.checks == []


def test_run_verify_unknown_keeps_tail() -> None:
    r = run_verify("", [_vc("bogus"), _vc("non_empty")])
    assert r.passed is False
    assert r.failures[0] == "unknown check: bogus"
    assert any("non_empty" in f for f in r.failures)
    assert [c.check for c in r.checks] == ["bogus", "non_empty"]
    assert r.checks[0].skipped is True
    assert r.checks[0].passed is False
    assert r.checks[0].source == "builtin"
    assert r.checks[1].skipped is False
    assert r.checks[1].passed is False
    assert r.checks[1].source == "builtin"


def test_run_verify_sync_fail_closed_on_custom() -> None:
    r = run_verify("hello", [_vc("custom:abc"), _vc("non_empty")])
    assert r.passed is False
    assert "custom check requires async verify" in r.failures[0]
    assert [c.check for c in r.checks] == ["custom:abc", "non_empty"]
    assert r.checks[0].skipped is True
    assert r.checks[0].passed is False
    assert r.checks[0].source == "custom"
    assert r.checks[1].skipped is False
    assert r.checks[1].passed is True


def test_validate_verify_check_accepts_custom_ref() -> None:
    assert validate_verify_check("custom:abc123") is None
    assert validate_verify_check("custom", {"id": "abc123"}) is None
    assert validate_verify_check("custom", {}) == "custom check requires id"
    assert validate_verify_check("custom:") == "custom check requires id"


def test_registered_checks_exclude_llm_judge() -> None:
    known = registered_checks()
    assert "custom" not in known
    assert all(not item.startswith("custom:") for item in known)


def test_validate_config_accepts_custom_check_id() -> None:
    config = SkillConfig(
        name="Judge",
        description="x",
        system_prompt="do it",
        allowed_tools=["read_document"],
        model="test",
        verify_checks=[VerifyCheck(check="custom:abc123")],
    )
    assert _validate_config(config, ["read_document"], registered_checks()) == []


class _JudgeProvider:
    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)
        self.requests: list[dict] = []

    async def complete(
        self,
        model: str,
        messages: list[Message],
        tools=None,
        temperature: float = 0.0,
        **kwargs,
    ) -> CompletionResult:
        self.requests.append(
            {"model": model, "messages": messages, "tools": tools}
        )
        if not self.answers:
            raise AssertionError("judge script exhausted")
        return CompletionResult(
            content=self.answers.pop(0),
            tool_calls=[],
            finish_reason="stop",
        )


def _mem_db() -> Database:
    db = Database(":memory:")
    db.init_schema()
    return db


def test_run_verify_async_skips_judge_when_deterministic_fails() -> None:
    db = _mem_db()
    row = create_custom_check(db, name="Has Python", prompt="есть опыт Python")
    provider = _JudgeProvider(["PASS"])
    result = asyncio.run(
        run_verify_async(
            "   ",
            [_vc("non_empty"), _vc(f"custom:{row.id}")],
            db=db,
            provider=provider,
            model="test/model",
        )
    )
    assert result.passed is False
    assert any("empty" in f for f in result.failures)
    assert provider.requests == []
    assert [c.check for c in result.checks] == ["non_empty", f"custom:{row.id}"]
    assert result.checks[0].passed is False
    assert result.checks[0].skipped is False
    assert result.checks[0].source == "builtin"
    assert result.checks[1].skipped is True
    assert result.checks[1].passed is False
    assert result.checks[1].source == "custom"


def test_run_verify_async_hidden_custom_fails_closed() -> None:
    db = _mem_db()
    row = create_custom_check(db, name="Has Python", prompt="есть опыт Python")
    hide_custom_check(db, row.id)
    provider = _JudgeProvider(["PASS"])
    result = asyncio.run(
        run_verify_async(
            "hello",
            [_vc(f"custom:{row.id}")],
            db=db,
            provider=provider,
            model="test/model",
        )
    )
    assert result.passed is False
    assert result.failures == [f"hidden custom check: {row.id!r}"]
    assert provider.requests == []
    assert len(result.checks) == 1
    assert result.checks[0].check == f"custom:{row.id}"
    assert result.checks[0].passed is False
    assert result.checks[0].skipped is False
    assert result.checks[0].source == "custom"
    assert result.checks[0].reason == f"hidden custom check: {row.id!r}"


def test_run_verify_async_unknown_custom_fails_closed() -> None:
    db = _mem_db()
    provider = _JudgeProvider(["PASS"])
    result = asyncio.run(
        run_verify_async(
            "hello",
            [_vc("custom:deadbeef")],
            db=db,
            provider=provider,
            model="test/model",
        )
    )
    assert result.passed is False
    assert result.failures == ["unknown custom check: 'deadbeef'"]
    assert provider.requests == []
    assert result.checks[0].check == "custom:deadbeef"
    assert result.checks[0].passed is False
    assert result.checks[0].skipped is False
    assert result.checks[0].source == "custom"


def test_run_verify_async_judge_runs_after_deterministic_pass() -> None:
    db = _mem_db()
    row = create_custom_check(db, name="Has Python", prompt="есть опыт Python")
    provider = _JudgeProvider(["PASS"])
    result = asyncio.run(
        run_verify_async(
            "hello",
            [_vc("non_empty"), _vc("custom", id=row.id)],
            db=db,
            provider=provider,
            model="test/model",
        )
    )
    assert result.passed is True
    assert result.failures == []
    assert [c.check for c in result.checks] == ["non_empty", "custom"]
    assert [c.passed for c in result.checks] == [True, True]
    assert [c.skipped for c in result.checks] == [False, False]
    assert result.checks[1].source == "custom"
    assert result.checks[1].reason is None
    assert result.checks[1].params == {"id": row.id}
    assert len(provider.requests) == 1
    messages = provider.requests[0]["messages"]
    assert all(m.role == "user" for m in messages)
    assert "есть опыт Python" in messages[0].content
    assert "hello" in messages[0].content
    assert provider.requests[0]["tools"] is None


def test_run_verify_async_judge_fail() -> None:
    db = _mem_db()
    row = create_custom_check(db, name="Has Python", prompt="есть опыт Python")
    provider = _JudgeProvider(["FAIL: нет стека"])
    result = asyncio.run(
        run_verify_async(
            "hello",
            [_vc(f"custom:{row.id}")],
            db=db,
            provider=provider,
            model="test/model",
        )
    )
    assert result.passed is False
    assert result.failures == ["custom:Has Python: нет стека"]
    assert len(result.checks) == 1
    assert result.checks[0].source == "custom"
    assert result.checks[0].passed is False
    assert result.checks[0].skipped is False
    assert result.checks[0].reason == "custom:Has Python: нет стека"


def test_run_custom_judge_missing_model() -> None:
    provider = _JudgeProvider(["PASS"])
    reason = asyncio.run(
        run_custom_judge(
            "hello",
            "есть опыт Python",
            provider=provider,
            model="",
        )
    )
    assert reason == "custom:preview: missing model"
    assert provider.requests == []
