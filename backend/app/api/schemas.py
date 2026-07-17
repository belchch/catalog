"""Pydantic v2 request/response schemas for the API routers."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


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
    # Derived capability tags (CATALOG-8): "python" (deterministic code) and/or
    # "ai" (LLM-driven). Computed from the config by the skills endpoint.
    tags: list[str] = Field(default_factory=list)


class ApplyRequest(BaseModel):
    """Apply a skill to one or more documents (CATALOG-4).

    Preferred form: ``doc_ids`` (a list of >=1 document id). For backward
    compatibility a single ``doc_id`` is still accepted and normalized to a
    one-element list. At least one document must be supplied (else 422).
    """

    doc_ids: list[str] = Field(default_factory=list)
    doc_id: str | None = None

    @model_validator(mode="after")
    def _normalize_doc_ids(self) -> ApplyRequest:
        if not self.doc_ids and self.doc_id is not None:
            self.doc_ids = [self.doc_id]
        if not self.doc_ids:
            raise ValueError("at least one document id is required (doc_ids or doc_id)")
        return self


class RunOut(BaseModel):
    id: str
    skill_id: str
    input_doc_id: str | None = None
    # All input documents (CATALOG-4); falls back to [input_doc_id] for legacy
    # rows written before the multi-doc column existed.
    input_doc_ids: list[str] | None = None
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
    # Preview of the generated config so the UI can populate the settings
    # modal before the user finalizes (CATALOG-6).
    config: SkillPreview


class SkillPreview(BaseModel):
    name: str
    description: str | None = None
    kind: str = "agent"
    model: str
    provider: str = ""
    reasoning: str = ""
    input_arity: int | None = None
    allowed_tools: list[str] = Field(default_factory=list)


class SkillConfigureRequest(BaseModel):
    """User adjustments applied in the pre-save settings modal (CATALOG-6).

    Only the supplied fields are overridden; the rest of the config is kept.
    """

    model: str | None = None
    provider: str | None = None
    reasoning: str | None = None


class ModelOut(BaseModel):
    id: str
    name: str
    context_length: int | None = None
    supports_reasoning: bool = False
    reasoning_variants: list[str] = Field(default_factory=list)


class ProviderOut(BaseModel):
    id: str
    name: str
    active: bool = False


class SettingsOut(BaseModel):
    """Current runtime provider/model selection (CATALOG-14)."""

    provider: str
    model: str


class SettingsUpdate(BaseModel):
    """Override the runtime active provider and/or model (CATALOG-14)."""

    provider: str | None = None
    model: str | None = None
