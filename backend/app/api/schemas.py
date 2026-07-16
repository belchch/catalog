"""Pydantic v2 request/response schemas for the API routers."""

from __future__ import annotations

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: str
    title: str
    kind: str
    created_at: str


class SkillOut(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    created_at: str
    kind: str = "agent"


class ApplyRequest(BaseModel):
    doc_id: str


class RunOut(BaseModel):
    id: str
    skill_id: str
    input_doc_id: str | None = None
    output_doc_id: str | None = None
    status: str
    # Trace is a JSON array of TraceEntry dicts (see Trace.to_json).
    trace: list | None = None


class BuildSkillRequest(BaseModel):
    session_id: str


class CommitOut(BaseModel):
    id: str
    status: str


class SessionCreated(BaseModel):
    id: str


class RunCreated(BaseModel):
    run_id: str


class SkillBuilt(BaseModel):
    skill_id: str
