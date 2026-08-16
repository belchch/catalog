from __future__ import annotations

import hashlib
import re
from collections.abc import AsyncIterator
from typing import Any

from catalog.agent.registry import ToolRegistry
from catalog.llm.base import (
    CompletionResult,
    LLMProvider,
    Message,
    ModelInfo,
    StreamDelta,
    ToolSpec,
)
from catalog.skills.apply import apply_skill_collect
from catalog.skills.repo_skill import SkillRecord
from catalog.storage.db import Database
from catalog.storage.repo_session_skill import list_session_skills

SESSION_TOOL_PARENT_RUN_ID = "session"

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_RESERVED = frozenset(
    {
        "list_documents",
        "read_document",
        "save_skill_prompt",
        "save_skill_script",
        "set_skill_meta",
        "save_skill_steps",
        "read_skill_draft",
    }
)


class _UnusedProvider:
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
        raise RuntimeError("script session tool does not call the LLM")

    async def stream_complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        reasoning: str = "",
    ) -> AsyncIterator[StreamDelta]:
        if False:
            yield StreamDelta(content="")
        raise RuntimeError("script session tool does not call the LLM")


def skill_tool_name(skill: SkillRecord, *, used: set[str]) -> str:
    base = _SLUG_RE.sub("_", skill.name.strip().lower()).strip("_") or "skill"
    name = f"skill_{base}"
    if name in _RESERVED or name in used:
        name = f"skill_{base}_{skill.id[:8]}"
    while name in used or name in _RESERVED:
        name = f"{name}_x"
    used.add(name)
    return name


def config_hash(config_json: str) -> str:
    return hashlib.sha256(config_json.encode("utf-8")).hexdigest()[:16]


def build_session_skill_tools(
    db: Database,
    session_id: str,
    *,
    workspace_dir: str,
    base_tools: ToolRegistry,
    reserved: set[str] | None = None,
    provider: LLMProvider | None = None,
    fallback_model: str = "",
    providers: dict[str, LLMProvider] | None = None,
) -> ToolRegistry:
    reg = ToolRegistry()
    used: set[str] = set(reserved or ())
    resolved_provider: LLMProvider = provider or _UnusedProvider()
    for skill in list_session_skills(db, session_id):
        if skill.config.kind != "script":
            continue
        tool_name = skill_tool_name(skill, used=used)
        pinned_hash = config_hash(skill.config.to_json())
        skill_id = skill.id
        skill_config = skill.config
        description = (
            (skill.description or skill.name).strip()
            or f"Run frozen script skill {skill.name!r}"
        )
        n_checks = len(skill_config.verify_checks)
        description = (
            f"{description} (script"
            + (f", {n_checks} verify checks" if n_checks else "")
            + f"; pinned={pinned_hash})"
        )

        async def _run(
            *,
            text: str = "",
            texts: list[str] | None = None,
            _skill_id: str = skill_id,
            _config=skill_config,
            _hash: str = pinned_hash,
            _name: str = skill.name,
        ) -> dict[str, Any]:
            if texts is not None:
                input_texts = [str(t) for t in texts]
            elif text:
                input_texts = [text]
            else:
                return {
                    "ok": False,
                    "error": "provide text or texts",
                    "skill_id": _skill_id,
                    "config_hash": _hash,
                }
            if not input_texts:
                return {
                    "ok": False,
                    "error": "provide text or texts",
                    "skill_id": _skill_id,
                    "config_hash": _hash,
                }
            try:
                result = await apply_skill_collect(
                    provider=resolved_provider,
                    db=db,
                    workspace_dir=workspace_dir,
                    skill=_config,
                    skill_id=_skill_id,
                    input_doc_ids=[],
                    base_tools=base_tools,
                    session_id=session_id,
                    input_texts=input_texts,
                    persist=False,
                    parent_run_id=SESSION_TOOL_PARENT_RUN_ID,
                    fallback_model=fallback_model,
                    providers=providers,
                )
            except Exception as exc:
                return {
                    "ok": False,
                    "error": str(exc),
                    "skill_id": _skill_id,
                    "skill_name": _name,
                    "config_hash": _hash,
                }
            verify_failures: list[str] = []
            for entry in result.trace.entries:
                if entry.kind == "verify" and not entry.data.get("passed", True):
                    verify_failures.extend(entry.data.get("failures") or [])
            return {
                "ok": result.status == "ok",
                "status": result.status,
                "run_id": result.run_id,
                "skill_id": _skill_id,
                "skill_name": _name,
                "config_hash": _hash,
                "verify_failures": verify_failures,
                "text": result.result_text,
            }

        reg.register(
            ToolSpec(
                name=tool_name,
                description=description,
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Single input text for the skill",
                        },
                        "texts": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Multiple input texts when input_arity > 1",
                        },
                    },
                },
            ),
            _run,
        )
    return reg
