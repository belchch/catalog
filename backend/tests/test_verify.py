from __future__ import annotations

from app.skills.config import VerifyCheck
from app.skills.verify import VerifyResult, run_verify


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


def test_run_verify_empty_checks_passes() -> None:
    # No checks → vacuously passes.
    r = run_verify("anything", [])
    assert r.passed is True
    assert isinstance(r, VerifyResult)


def test_run_verify_unknown_short_circuits() -> None:
    # Even if later checks would fail, unknown check is reported alone.
    r = run_verify("", [_vc("non_empty"), _vc("bogus")])
    assert r.passed is False
    assert r.failures == ["unknown check: bogus"]
