from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from app.documents.ingest import ingest_file
from app.documents.obsidian import (
    build_title_to_stem_map,
    ensure_parent_wikilinks,
    rewrite_wiki_links,
)
from app.documents.tools import build_document_tools
from app.llm.base import CompletionResult, Message, ModelInfo, StreamDelta, ToolSpec
from app.skills.apply import apply_skill_collect
from app.skills.config import SkillConfig, VerifyCheck
from app.skills.repo_skill import create_skill
from app.storage.db import Database
from app.storage.repo_document import create_document, get_document


class ScriptProvider:
    def __init__(self, script: list[CompletionResult]) -> None:
        self.script: list[CompletionResult] = list(script)

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        tool_choice: str = "auto",
        reasoning: str = "",
    ) -> CompletionResult:
        return self.script.pop(0)

    async def stream_complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        reasoning: str = "",
    ) -> Any:
        yield StreamDelta(content="")


@pytest.fixture()
def db() -> Database:
    d = Database(":memory:")
    d.init_schema()
    return d


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    return tmp_path


def _result(content: str) -> CompletionResult:
    return CompletionResult(content=content, tool_calls=[], finish_reason="stop")


def test_ensure_parent_wikilinks_single() -> None:
    out = ensure_parent_wikilinks("body", ["cover-letter-ea411722"])
    assert "[[cover-letter-ea411722]]" in out
    assert "Источник: [[cover-letter-ea411722]]" in out
    assert out.startswith("body")


def test_ensure_parent_wikilinks_multiple() -> None:
    out = ensure_parent_wikilinks(
        "body",
        ["parent-aaa11111", "parent-bbb22222"],
    )
    assert "[[parent-aaa11111]]" in out
    assert "[[parent-bbb22222]]" in out
    assert "Источники:" in out
    assert out.index("[[parent-aaa11111]]") < out.index("[[parent-bbb22222]]")


def test_ensure_parent_wikilinks_idempotent_when_present() -> None:
    text = "see [[cover-letter-ea411722]] already"
    assert ensure_parent_wikilinks(text, ["cover-letter-ea411722"]) == text


def test_ensure_parent_wikilinks_prefix_stem_not_enough() -> None:
    text = "see [[foo-123456789abc]] already"
    out = ensure_parent_wikilinks(text, ["foo-12345678"])
    assert "Источник: [[foo-12345678]]" in out
    assert "[[foo-123456789abc]]" in out


def test_ensure_parent_wikilinks_alias_counts_as_present() -> None:
    text = "see [[cover-letter-ea411722|письмо]]"
    assert ensure_parent_wikilinks(text, ["cover-letter-ea411722"]) == text


def test_ensure_parent_wikilinks_heading_counts_as_present() -> None:
    text = "see [[cover-letter-ea411722#Intro]]"
    assert ensure_parent_wikilinks(text, ["cover-letter-ea411722"]) == text


def test_ensure_parent_wikilinks_only_missing() -> None:
    text = "see [[parent-aaa11111]]"
    out = ensure_parent_wikilinks(
        text, ["parent-aaa11111", "parent-bbb22222"]
    )
    assert out.count("[[parent-aaa11111]]") == 1
    assert "Источник: [[parent-bbb22222]]" in out


def test_ensure_parent_wikilinks_empty_text() -> None:
    out = ensure_parent_wikilinks("", ["parent-aaa11111"])
    assert out == "Источник: [[parent-aaa11111]]\n"


def test_ensure_parent_wikilinks_dedupes_stems() -> None:
    out = ensure_parent_wikilinks("body", ["same-stem", "same-stem"])
    assert out.count("[[same-stem]]") == 1


def test_rewrite_wiki_links_title_to_stem() -> None:
    mapping = {"Экономия токенов": "ekonomiya-tokov-abc12345"}
    assert (
        rewrite_wiki_links("[[Экономия токенов]] abc", mapping)
        == "[[ekonomiya-tokov-abc12345]] abc"
    )


def test_rewrite_wiki_links_alias() -> None:
    mapping = {"Экономия токенов": "ekonomiya-tokov-abc12345"}
    assert (
        rewrite_wiki_links("[[Экономия токенов|раздел]]", mapping)
        == "[[ekonomiya-tokov-abc12345|раздел]]"
    )


def test_rewrite_wiki_links_heading() -> None:
    mapping = {"Экономия токенов": "ekonomiya-tokov-abc12345"}
    assert (
        rewrite_wiki_links("[[Экономия токенов#Введение]]", mapping)
        == "[[ekonomiya-tokov-abc12345#Введение]]"
    )


def test_rewrite_wiki_links_heading_and_alias() -> None:
    mapping = {"Экономия токенов": "ekonomiya-tokov-abc12345"}
    assert (
        rewrite_wiki_links("[[Экономия токенов#Введение|раздел]]", mapping)
        == "[[ekonomiya-tokov-abc12345#Введение|раздел]]"
    )


def test_rewrite_wiki_links_unknown_unchanged() -> None:
    mapping = {"Экономия токенов": "ekonomiya-tokov-abc12345"}
    assert rewrite_wiki_links("[[unknown]]", mapping) == "[[unknown]]"


def test_rewrite_wiki_links_already_stem_unchanged() -> None:
    mapping = {"Экономия токенов": "ekonomiya-tokov-abc12345"}
    assert (
        rewrite_wiki_links("[[ekonomiya-tokov-abc12345]]", mapping)
        == "[[ekonomiya-tokov-abc12345]]"
    )


def test_rewrite_wiki_links_special_chars_in_title() -> None:
    mapping = {"A & B (draft)": "a-b-draft-abc12345"}
    assert (
        rewrite_wiki_links("see [[A & B (draft)]] please", mapping)
        == "see [[a-b-draft-abc12345]] please"
    )


def test_build_title_to_stem_map(db: Database) -> None:
    create_document(
        db,
        title="Экономия токенов",
        path="documents/ekonomiya-tokov-abc12345.md",
        kind="md",
    )
    create_document(
        db,
        title="Cover letter",
        path="documents/cover-letter-spiiran-ntbvt-java-ea411722.md",
        kind="md",
    )
    mapping = build_title_to_stem_map(db)
    assert mapping["Экономия токенов"] == "ekonomiya-tokov-abc12345"
    assert mapping["Cover letter"] == "cover-letter-spiiran-ntbvt-java-ea411722"


def test_build_title_to_stem_map_skips_ambiguous_duplicates(db: Database) -> None:
    create_document(
        db,
        title="Cover letter",
        path="documents/cover-letter-aaa11111.md",
        kind="md",
    )
    create_document(
        db,
        title="Cover letter",
        path="documents/cover-letter-bbb22222.md",
        kind="md",
    )
    create_document(
        db,
        title="Unique",
        path="documents/unique-ccc33333.md",
        kind="md",
    )
    mapping = build_title_to_stem_map(db)
    assert "Cover letter" not in mapping
    assert mapping["Unique"] == "unique-ccc33333"
    assert (
        rewrite_wiki_links("[[Cover letter]] and [[Unique]]", mapping)
        == "[[Cover letter]] and [[unique-ccc33333]]"
    )


def test_apply_persist_rewrites_obsidian_links(
    db: Database, workspace: Path
) -> None:
    linked = create_document(
        db,
        title="Экономия токенов",
        path="documents/ekonomiya-tokov-abc12345.md",
        kind="md",
    )
    (workspace / "documents").mkdir(parents=True, exist_ok=True)
    (workspace / linked.path).write_text("token savings", encoding="utf-8")

    input_doc = ingest_file(
        db, workspace, filename="input.md", content=b"source text"
    )
    skill = SkillConfig(
        name="linker",
        description="test",
        system_prompt="Link docs.",
        allowed_tools=["read_document"],
        model="test/model",
        temperature=0.0,
        max_iterations=4,
        max_retries=0,
        verify_checks=[VerifyCheck("non_empty")],
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    provider = ScriptProvider(
        [_result("См. [[Экономия токенов]] и [[unknown]].")]
    )

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc.id],
            base_tools=build_document_tools(db, workspace),
        )
    )

    assert result.status == "ok"
    assert result.output_doc_id is not None
    assert "[[ekonomiya-tokov-abc12345]]" in (result.result_text or "")
    assert "[[Экономия токенов]]" not in (result.result_text or "")
    assert "[[unknown]]" in (result.result_text or "")

    out_doc = get_document(db, result.output_doc_id)
    assert out_doc is not None
    file_text = (workspace / out_doc.path).read_text(encoding="utf-8")
    assert "[[ekonomiya-tokov-abc12345]]" in file_text
    assert "[[Экономия токенов]]" not in file_text
    input_stem = Path(input_doc.path).stem
    assert f"[[{input_stem}]]" in file_text


def test_apply_persist_ensures_parent_wikilinks(
    db: Database, workspace: Path
) -> None:
    input_doc = ingest_file(
        db, workspace, filename="cover-letter.md", content=b"source text"
    )
    input_stem = Path(input_doc.path).stem
    skill = SkillConfig(
        name="no-links",
        description="test",
        system_prompt="Write summary.",
        allowed_tools=["read_document"],
        model="test/model",
        temperature=0.0,
        max_iterations=4,
        max_retries=0,
        verify_checks=[VerifyCheck("non_empty")],
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    provider = ScriptProvider([_result("Summary without any wiki links.")])

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc.id],
            base_tools=build_document_tools(db, workspace),
        )
    )

    assert result.status == "ok"
    assert result.output_doc_id is not None
    assert f"[[{input_stem}]]" in (result.result_text or "")

    out_doc = get_document(db, result.output_doc_id)
    assert out_doc is not None
    file_text = (workspace / out_doc.path).read_text(encoding="utf-8")
    assert f"Источник: [[{input_stem}]]" in file_text


def test_apply_persist_ensures_all_parent_wikilinks(
    db: Database, workspace: Path
) -> None:
    doc_a = ingest_file(
        db, workspace, filename="alpha.md", content=b"alpha"
    )
    doc_b = ingest_file(
        db, workspace, filename="beta.md", content=b"beta"
    )
    stems = [Path(doc_a.path).stem, Path(doc_b.path).stem]
    skill = SkillConfig(
        name="multi",
        description="test",
        system_prompt="Write summary.",
        allowed_tools=["read_document"],
        model="test/model",
        temperature=0.0,
        max_iterations=4,
        max_retries=0,
        verify_checks=[VerifyCheck("non_empty")],
        input_arity=2,
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    provider = ScriptProvider([_result("Combined summary.")])

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[doc_a.id, doc_b.id],
            base_tools=build_document_tools(db, workspace),
        )
    )

    assert result.status == "ok"
    assert result.output_doc_id is not None
    out_doc = get_document(db, result.output_doc_id)
    assert out_doc is not None
    file_text = (workspace / out_doc.path).read_text(encoding="utf-8")
    for stem in stems:
        assert f"[[{stem}]]" in file_text


def test_apply_prompt_mentions_file_stem(
    db: Database, workspace: Path
) -> None:
    input_doc = ingest_file(
        db, workspace, filename="input.md", content=b"source text"
    )
    skill = SkillConfig(
        name="linker",
        description="test",
        system_prompt="Link docs.",
        allowed_tools=["read_document"],
        model="test/model",
        temperature=0.0,
        max_iterations=4,
        max_retries=0,
        verify_checks=[],
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    seen: list[str] = []
    provider = ScriptProvider([_result("ok")])
    original_complete = provider.complete

    async def capturing_complete(*args, **kwargs):
        messages = kwargs.get("messages") or args[1]
        for m in messages:
            if m.role == "user" and isinstance(m.content, str):
                seen.append(m.content)
        return await original_complete(*args, **kwargs)

    provider.complete = capturing_complete  # type: ignore[method-assign]

    asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc.id],
            base_tools=build_document_tools(db, workspace),
        )
    )

    assert seen
    assert "имя файла" in seen[0]
    assert Path(input_doc.path).stem in seen[0]
