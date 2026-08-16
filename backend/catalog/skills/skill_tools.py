from __future__ import annotations

import hashlib
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from catalog.agent.registry import ToolRegistry
from catalog.agent.trace import Trace, TraceEntry
from catalog.llm.base import (
    CompletionResult,
    LLMProvider,
    Message,
    ModelInfo,
    StreamDelta,
    ToolSpec,
)
from catalog.skills.apply import apply_skill_collect
from catalog.skills.budget import (
    SkillBudget,
    estimate_skill_budget,
    estimate_skill_llm_calls,
    nested_skill_hold,
)
from catalog.skills.config import SKILL_KINDS
from catalog.skills.verify import is_custom_check_id
from catalog.skills.repo_run import create_run, finish_run
from catalog.skills.repo_skill import SkillRecord
from catalog.storage.db import Database
from catalog.storage.repo_session_skill import list_session_skills

SESSION_TOOL_PARENT_RUN_ID = "session"


@dataclass(frozen=True)
class SkillCallContext:
    depth: int = 0
    chain: tuple[str, ...] = ()

    def nested(self, skill_id: str) -> SkillCallContext:
        return SkillCallContext(
            depth=self.depth + 1,
            chain=self.chain + (skill_id,),
        )


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


def _merge_tools(*registries: ToolRegistry) -> ToolRegistry:
    merged = ToolRegistry()
    for registry in registries:
        for name in registry.names():
            entry = registry.get(name)
            if entry is not None:
                merged.register(entry[0], entry[1])
    return merged


def _deadline_exceeded_result(
    *,
    db: Database,
    session_id: str,
    skill_id: str,
    skill_name: str,
    pinned_hash: str,
    depth: int,
    run_id: str | None = None,
) -> dict[str, Any]:
    if run_id is None:
        run_id = create_run(
            db,
            skill_id=skill_id,
            session_id=session_id,
            persist=False,
            parent_run_id=SESSION_TOOL_PARENT_RUN_ID,
        )
        trace = Trace()
        trace.entries.append(
            TraceEntry("deadline", 0, {"error": "deadline exceeded"})
        )
        finish_run(db, run_id, status="failed", output_doc_id=None, trace=trace)
    return {
        "ok": False,
        "error": "deadline exceeded",
        "skill_id": skill_id,
        "skill_name": skill_name,
        "config_hash": pinned_hash,
        "depth": depth,
        "run_id": run_id,
    }


def _budget_exhausted_result(
    *,
    db: Database,
    session_id: str,
    skill_id: str,
    skill_name: str,
    pinned_hash: str,
    depth: int,
    budget: SkillBudget,
    needed_llm: int,
    needed_runs: int,
) -> dict[str, Any]:
    payload = {
        "llm_calls_left": budget.llm_calls_left,
        "nested_runs_left": budget.nested_runs_left,
        "needed_llm_calls": needed_llm,
        "needed_nested_runs": needed_runs,
    }
    run_id = create_run(
        db,
        skill_id=skill_id,
        session_id=session_id,
        persist=False,
        parent_run_id=SESSION_TOOL_PARENT_RUN_ID,
    )
    trace = Trace()
    trace.entries.append(TraceEntry("budget", 0, {"error": "budget exhausted", **payload}))
    finish_run(db, run_id, status="failed", output_doc_id=None, trace=trace)
    return {
        "ok": False,
        "error": "budget exhausted",
        "budget": payload,
        "skill_id": skill_id,
        "skill_name": skill_name,
        "config_hash": pinned_hash,
        "depth": depth,
        "run_id": run_id,
    }


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
    call_context: SkillCallContext | None = None,
    max_skill_depth: int = 2,
    budget: SkillBudget | None = None,
    kinds: frozenset[str] | None = None,
) -> ToolRegistry:
    ctx = call_context or SkillCallContext()
    reg = ToolRegistry()
    if ctx.depth >= max_skill_depth:
        return reg
    reserved_names = frozenset(reserved or ())
    used: set[str] = set(reserved_names)
    session_provider: LLMProvider = provider or _UnusedProvider()
    allowed_kinds = kinds if kinds is not None else frozenset(SKILL_KINDS)
    for skill in list_session_skills(db, session_id):
        if skill.id in ctx.chain:
            continue
        if skill.status != "committed":
            continue
        if skill.config.kind not in allowed_kinds:
            continue
        tool_name = skill_tool_name(skill, used=used)
        pinned_hash = config_hash(skill.config.to_json())
        skill_id = skill.id
        skill_config = skill.config
        skill_kind = skill_config.kind
        has_custom_verify = any(
            is_custom_check_id(check.check) for check in skill_config.verify_checks
        )
        if skill_kind == "script" and not has_custom_verify:
            skill_provider: LLMProvider = _UnusedProvider()
        else:
            skill_provider = session_provider
        description = (
            (skill.description or skill.name).strip()
            or f"Run frozen {skill_kind} skill {skill.name!r}"
        )
        n_checks = len(skill_config.verify_checks)
        cost = estimate_skill_llm_calls(skill_config)
        description = (
            f"{description} ({skill_kind}"
            + (f", {n_checks} verify checks" if n_checks else "")
            + f", ~{cost} LLM calls"
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
            _ctx: SkillCallContext = ctx,
            _max_depth: int = max_skill_depth,
            _reserved: frozenset[str] = reserved_names,
            _budget: SkillBudget | None = budget,
            _kinds: frozenset[str] = allowed_kinds,
            _provider: LLMProvider = skill_provider,
        ) -> dict[str, Any]:
            nested = _ctx.nested(_skill_id)
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
                    "depth": nested.depth,
                }
            if not input_texts:
                return {
                    "ok": False,
                    "error": "provide text or texts",
                    "skill_id": _skill_id,
                    "config_hash": _hash,
                    "depth": nested.depth,
                }
            hold = None
            if _budget is not None and _budget.mark_deadline_if_exceeded():
                return _deadline_exceeded_result(
                    db=db,
                    session_id=session_id,
                    skill_id=_skill_id,
                    skill_name=_name,
                    pinned_hash=_hash,
                    depth=nested.depth,
                )
            if _budget is not None:
                needed_llm, needed_runs = estimate_skill_budget(_config)
                hold = _budget.reserve(needed_llm, needed_runs)
                if hold is None:
                    return _budget_exhausted_result(
                        db=db,
                        session_id=session_id,
                        skill_id=_skill_id,
                        skill_name=_name,
                        pinned_hash=_hash,
                        depth=nested.depth,
                        budget=_budget,
                        needed_llm=needed_llm,
                        needed_runs=needed_runs,
                    )
            nested_skill_tools = build_session_skill_tools(
                db,
                session_id,
                workspace_dir=workspace_dir,
                base_tools=base_tools,
                reserved=_reserved | set(base_tools.names()),
                provider=provider,
                fallback_model=fallback_model,
                providers=providers,
                call_context=nested,
                max_skill_depth=_max_depth,
                budget=_budget,
                kinds=_kinds,
            )
            apply_tools = _merge_tools(base_tools, nested_skill_tools)
            try:
                with nested_skill_hold(hold, _budget):
                    result = await apply_skill_collect(
                        provider=_provider,
                        db=db,
                        workspace_dir=workspace_dir,
                        skill=_config,
                        skill_id=_skill_id,
                        input_doc_ids=[],
                        base_tools=apply_tools,
                        session_id=session_id,
                        input_texts=input_texts,
                        persist=False,
                        parent_run_id=SESSION_TOOL_PARENT_RUN_ID,
                        fallback_model=fallback_model,
                        providers=providers,
                        call_context=nested,
                    )
            except Exception as exc:
                return {
                    "ok": False,
                    "error": str(exc),
                    "skill_id": _skill_id,
                    "skill_name": _name,
                    "config_hash": _hash,
                    "depth": nested.depth,
                }
            finally:
                if _budget is not None and hold is not None:
                    _budget.release(hold)
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
                "depth": nested.depth,
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
