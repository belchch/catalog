from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from catalog.skills.config import SkillConfig


@dataclass
class SkillBudgetHold:
    llm_reserved: int
    runs_reserved: int
    llm_used: int = 0

    def charge_llm(self) -> None:
        self.llm_used += 1


@dataclass
class SkillBudget:
    llm_calls_left: int
    nested_runs_left: int

    def snapshot(self) -> dict[str, int]:
        return {
            "llm_calls_left": self.llm_calls_left,
            "nested_runs_left": self.nested_runs_left,
        }

    def reserve(self, llm_calls: int, nested_runs: int) -> SkillBudgetHold | None:
        if llm_calls < 0 or nested_runs < 0:
            return None
        if self.llm_calls_left < llm_calls or self.nested_runs_left < nested_runs:
            return None
        self.llm_calls_left -= llm_calls
        self.nested_runs_left -= nested_runs
        return SkillBudgetHold(llm_reserved=llm_calls, runs_reserved=nested_runs)

    def release(self, hold: SkillBudgetHold) -> None:
        unused = hold.llm_reserved - hold.llm_used
        if unused > 0:
            self.llm_calls_left += unused


_hold_stack: ContextVar[tuple[SkillBudgetHold, ...]] = ContextVar(
    "skill_budget_holds",
    default=(),
)


def estimate_skill_budget(skill: SkillConfig) -> tuple[int, int]:
    if skill.kind == "script":
        return 0, 1
    if skill.kind == "pipeline":
        return len(skill.steps) * skill.max_iterations, 1
    return skill.max_iterations * (skill.max_retries + 1), 1


def charge_nested_skill_llm() -> None:
    stack = _hold_stack.get()
    if stack:
        stack[-1].charge_llm()


@contextmanager
def nested_skill_hold(hold: SkillBudgetHold | None) -> Iterator[None]:
    if hold is None:
        yield
        return
    token = _hold_stack.set(_hold_stack.get() + (hold,))
    try:
        yield
    finally:
        _hold_stack.reset(token)
