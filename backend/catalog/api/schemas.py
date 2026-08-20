"""Pydantic v2 request/response schemas for the API routers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ScanReport(BaseModel):
    added: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    renamed: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)


class WorkspaceOut(BaseModel):
    path: str
    display_name: str | None = None
    last_opened: str | None = None


class WorkspaceOpenRequest(BaseModel):
    path: str
    confirm: bool = False


class WorkspaceOpenResult(BaseModel):
    status: Literal["ok", "needs_init", "needs_confirm"]
    path: str | None = None
    display_name: str | None = None
    scan: ScanReport | None = None


class WorkspaceBusyOut(BaseModel):
    busy: bool
    reason: Literal["run", "session"] | None = None


class FsEntry(BaseModel):
    name: str
    path: str
    has_catalog: bool = False


class DocumentOut(BaseModel):
    id: str
    title: str
    kind: str
    created_at: str


class ExportDocxRequest(BaseModel):
    doc_ids: list[str] = Field(min_length=1)
    title: str = ""
    template: str = ""

    @field_validator("doc_ids")
    @classmethod
    def _non_empty_doc_ids(cls, value: list[str]) -> list[str]:
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if not cleaned:
            raise ValueError("doc_ids must be a non-empty list")
        return cleaned


class ExportDocxOut(BaseModel):
    ok: bool
    path: str
    headings: int
    tables: int


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
    # Input mode (CATALOG-4): 1, 2, or null (= document list / any >= 1).
    input_arity: int | None = None
    provider: str | None = None
    model: str | None = None
    reasoning: str | None = None
    estimated_llm_calls: int = 0
    outputs_count: int = 0


class ApplyRequest(BaseModel):
    """Apply a skill to one or more documents (CATALOG-4).

    Preferred form: ``doc_ids`` (a list of >=1 document id). For backward
    compatibility a single ``doc_id`` is still accepted and normalized to a
    one-element list. At least one document must be supplied (else 422).

    ``persist`` (CATALOG-18) selects the output mode: ``True`` (default,
    matching pre-CATALOG-18 behaviour) auto-creates a ``result_md`` document
    on success ("в док"); ``False`` leaves the result on screen only
    ("на экран") — it can still be saved later via ``POST /runs/{id}/save``.

    ``prompt`` (CATALOG-56) is an optional runtime clarification for agent
    skills; whitespace-only values are normalized to ``None``. Script skills
    accept the field but ignore it at apply time.
    """

    doc_ids: list[str] = Field(default_factory=list)
    doc_id: str | None = None
    persist: bool = True
    session_id: str | None = None
    prompt: str | None = None

    @model_validator(mode="after")
    def _normalize_doc_ids(self) -> ApplyRequest:
        if not self.doc_ids and self.doc_id is not None:
            self.doc_ids = [self.doc_id]
        if not self.doc_ids:
            raise ValueError("at least one document id is required (doc_ids or doc_id)")
        if self.prompt is not None:
            stripped = self.prompt.strip()
            self.prompt = stripped or None
        return self


class RunOut(BaseModel):
    id: str
    skill_id: str
    input_doc_id: str | None = None
    # All input documents (CATALOG-4); falls back to [input_doc_id] for legacy
    # rows written before the multi-doc column existed.
    input_doc_ids: list[str] | None = None
    output_doc_id: str | None = None
    output_doc_ids: list[str] | None = None
    status: str
    # Trace is a JSON array of TraceEntry dicts (see Trace.to_json).
    trace: list | None = None
    # Raw agent/script output, kept even when persist=False (CATALOG-18).
    result_text: str | None = None
    result_artifacts: dict[str, str] | None = None
    parent_run_id: str | None = None


class BuildSkillRequest(BaseModel):
    session_id: str


class CommitOut(BaseModel):
    id: str
    status: str


class SessionCreateRequest(BaseModel):
    doc_ids: list[str] = Field(default_factory=list)


class SessionToolsAttachRequest(BaseModel):
    skill_ids: list[str] = Field(min_length=1)

    @field_validator("skill_ids")
    @classmethod
    def _non_empty_skill_ids(cls, value: list[str]) -> list[str]:
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if not cleaned:
            raise ValueError("skill_ids must be a non-empty list")
        return cleaned


class SessionToolsAttachResult(BaseModel):
    skipped_skill_ids: list[str] = Field(default_factory=list)
    skills: list[SkillOut] = Field(default_factory=list)


class SessionCreated(BaseModel):
    id: str
    skipped_doc_ids: list[str] = Field(default_factory=list)


class SessionOut(BaseModel):
    id: str
    status: str
    created_at: str
    updated_at: str
    title: str | None = None
    skill_id: str | None = None
    llm_timeout_seconds: int = 60


class SessionUpdate(BaseModel):
    llm_timeout_seconds: int = Field(..., ge=30, le=300)


class MessageOut(BaseModel):
    id: int
    session_id: str
    role: str
    content: str | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    created_at: str


class EditStarted(BaseModel):
    """Response of ``POST /skills/{id}/edit`` (CATALOG-17)."""

    session_id: str
    skill_id: str


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
    ``input_arity`` uses presence in the request body: omitted = leave
    unchanged; ``1`` / ``2`` = fixed count; ``null`` = document list (any >= 1).
    """

    model: str | None = None
    provider: str | None = None
    reasoning: str | None = None
    input_arity: int | None = None
    name: str | None = None

    @field_validator("input_arity")
    @classmethod
    def _allowed_input_arity(cls, value: int | None) -> int | None:
        if value is not None and value not in (1, 2):
            raise ValueError("input_arity must be 1, 2, or null (document list)")
        return value

    @field_validator("name")
    @classmethod
    def _non_empty_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must be non-empty")
        return stripped


class SkillRenameRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _non_empty_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must be non-empty")
        return stripped


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
    provider: str
    model: str
    keys_configured: bool = False


class SettingsUpdate(BaseModel):
    provider: str | None = None
    model: str | None = None


class ProviderSetupOut(BaseModel):
    id: str
    name: str
    configured: bool
    managed_by_env: bool
    active: bool = False


class SetupOut(BaseModel):
    keys_configured: bool
    provider: str
    openrouter_configured: bool
    zai_configured: bool
    providers: list[ProviderSetupOut] = Field(default_factory=list)



class SetupKeysUpdate(BaseModel):
    openrouter_api_key: str | None = None
    zai_api_key: str | None = None


class ScriptDryRunStatus(BaseModel):
    slot: str
    sha256: str
    ok: bool
    stage: Literal["validate", "run", "verify"] | None = None
    error: str | None = None
    time: str | None = None


class SessionArtifactOut(BaseModel):
    type: str
    content: str
    is_valid: bool
    error: str | None = None
    source: str
    updated_at: str
    dry_run: ScriptDryRunStatus | list[ScriptDryRunStatus] | None = None


class ArtifactPatchRequest(BaseModel):
    content: str


class ScriptTryRequest(BaseModel):
    code: str | None = None
    doc_ids: list[str] | None = None
    step_index: int | None = None


class ScriptTryOut(BaseModel):
    ok: bool
    stage: Literal["validate", "run", "verify"] | None = None
    error: str | None = None
    input_preview: str = ""
    input_len: int = 0
    output_preview: str = ""
    output_len: int = 0
    output_kind: Literal["str", "list", "dict"] | None = None
    duration_ms: int = 0
    verify: dict | None = None
    line_no: int | None = None
    source_line: str | None = None


class SkillMetaPatchRequest(BaseModel):
    name: str
    description: str
    kind: str
    input_arity: int | None = None
    allowed_tools: list[str] = Field(default_factory=list)
    verify_checks: list[dict] = Field(default_factory=list)

    @field_validator("kind")
    @classmethod
    def _allowed_kind(cls, value: str) -> str:
        if value not in ("agent", "script", "pipeline"):
            raise ValueError("kind must be 'agent', 'script', or 'pipeline'")
        return value

    @field_validator("name")
    @classmethod
    def _non_empty_meta_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must be non-empty")
        return stripped

    @field_validator("input_arity")
    @classmethod
    def _allowed_input_arity(cls, value: int | None) -> int | None:
        if value is not None and value not in (1, 2):
            raise ValueError("input_arity must be 1, 2, or null (document list)")
        return value


class SkillTrack(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    input_arity: int | None = None
    rationale: str = Field(min_length=1)

    @field_validator("name", "description", "operation", "rationale")
    @classmethod
    def _strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must be non-empty")
        return stripped

    @field_validator("input_arity")
    @classmethod
    def _allowed_track_arity(cls, value: int | None) -> int | None:
        if value is not None and value not in (1, 2):
            raise ValueError("input_arity must be 1, 2, or null (document list)")
        return value


class SkillTracksOut(BaseModel):
    tracks: list[SkillTrack] = Field(default_factory=list)
    skipped: bool = False
    fallback: bool = False


class SkillTrackSelectRequest(BaseModel):
    track: SkillTrack


class SkillTrackSelected(BaseModel):
    session_id: str
    content: str


class CustomCheckOut(BaseModel):
    id: str
    name: str
    prompt: str
    hidden: bool
    created_at: str


class CustomCheckCreate(BaseModel):
    name: str
    prompt: str

    @field_validator("name", "prompt")
    @classmethod
    def _non_empty_check_field(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must be non-empty")
        return stripped


class CustomCheckPreviewRequest(BaseModel):
    prompt: str
    sample: str

    @field_validator("prompt")
    @classmethod
    def _non_empty_preview_prompt(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("prompt must be non-empty")
        return stripped


class CustomCheckPreviewOut(BaseModel):
    passed: bool
    failures: list[str] = Field(default_factory=list)


class VerifyChecksCatalogOut(BaseModel):
    builtin: list[str]
    labels: dict[str, str]
