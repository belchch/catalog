"""Skill layer: frozen agent configs, deterministic verify, and apply loop.

A *skill* is a frozen agent configuration (``SkillConfig``) plus a set of
deterministic ``verify`` checks. :func:`apply_skill` runs the agent loop with
retry-on-verify-failure and persists the result as a ``Document(result_md)``.
"""

from app.skills.apply import ApplyResult, apply_skill, apply_skill_collect
from app.skills.config import SkillConfig, VerifyCheck
from app.skills.repo_run import create_run, finish_run, get_run
from app.skills.repo_skill import (
    SkillRecord,
    create_skill,
    get_skill,
    list_skills,
    update_status,
)
from app.skills.verify import CheckFn, VerifyResult, register_check, run_verify

__all__ = [
    "ApplyResult",
    "CheckFn",
    "SkillConfig",
    "SkillRecord",
    "VerifyCheck",
    "VerifyResult",
    "apply_skill",
    "apply_skill_collect",
    "create_run",
    "create_skill",
    "finish_run",
    "get_run",
    "get_skill",
    "list_skills",
    "register_check",
    "run_verify",
    "update_status",
]
