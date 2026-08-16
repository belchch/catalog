from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from catalog.skills.config import SkillConfig

TURN_DEADLINE_FLOOR_SECONDS = 600
TURN_DEADLINE_TIMEOUT_FACTOR = 15


def turn_deadline_seconds(llm_timeout_seconds: int) -> int:
    return max(
        TURN_DEADLINE_FLOOR_SECONDS,
        int(llm_timeout_seconds) * TURN_DEADLINE_TIMEOUT_FACTOR,
    )


def make_turn_budget(
    *,
    llm_calls_left: int,
    nested_runs_left: int,
    llm_timeout_seconds: int,
    now: float | None = None,
) -> SkillBudget:
    started = time.monotonic() if now is None else now
    return SkillBudget(
        llm_calls_left=llm_calls_left,
        nested_runs_left=nested_runs_left,
        deadline_monotonic=started + turn_deadline_seconds(llm_timeout_seconds),
    )


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
    deadline_monotonic: float | None = None
    deadline_hit: bool = False

    def snapshot(self) -> dict[str, int]:
        return {
            "llm_calls_left": self.llm_calls_left,
            "nested_runs_left": self.nested_runs_left,
        }

    def mark_deadline_if_exceeded(self, now: float | None = None) -> bool:
        if self.deadline_monotonic is None:
            return False
        current = time.monotonic() if now is None else now
        if current >= self.deadline_monotonic:
            self.deadline_hit = True
            return True
        return False

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
_active_budget: ContextVar[SkillBudget | None] = ContextVar(
    "skill_budget_active",
    default=None,
)


def estimate_skill_llm_calls(skill: SkillConfig) -> int:
    from catalog.skills.verify import is_custom_check_id

    if skill.kind == "script":
        base = 0
    elif skill.kind == "pipeline":
        base = len(skill.steps) * skill.max_iterations
    else:
        base = skill.max_iterations * (skill.max_retries + 1)
    n_custom = sum(
        1 for check in skill.verify_checks if is_custom_check_id(check.check)
    )
    if n_custom == 0:
        return base
    if skill.kind == "agent":
        return base + n_custom * (skill.max_retries + 1)
    return base + n_custom


def estimate_skill_budget(skill: SkillConfig) -> tuple[int, int]:
    return estimate_skill_llm_calls(skill), 1


def charge_nested_skill_llm() -> None:
    stack = _hold_stack.get()
    if stack:
        stack[-1].charge_llm()


def nested_deadline_exceeded(now: float | None = None) -> bool:
    budget = _active_budget.get()
    if budget is None:
        return False
    return budget.mark_deadline_if_exceeded(now)


@contextmanager
def nested_skill_hold(
    hold: SkillBudgetHold | None,
    budget: SkillBudget | None = None,
) -> Iterator[None]:
    if hold is None and budget is None:
        yield
        return
    hold_token = None
    budget_token = None
    if hold is not None:
        hold_token = _hold_stack.set(_hold_stack.get() + (hold,))
    if budget is not None:
        budget_token = _active_budget.set(budget)
    try:
        yield
    finally:
        if budget_token is not None:
            _active_budget.reset(budget_token)
        if hold_token is not None:
            _hold_stack.reset(hold_token)
