// Thin fetch wrappers for the Catalog backend (step 06).
// Base URL comes from VITE_API_URL with a safe default for local dev.

export interface DocumentOut {
  id: string
  title: string
  kind: string
  created_at: string
}

export interface SkillOut {
  id: string
  name: string
  description: string | null
  status: string
  created_at: string
  kind: string
  // Derived capability tags (CATALOG-8): "python" (deterministic code) and/or
  // "ai" (LLM-driven). Computed by the backend from the skill config.
  tags: string[]
  input_arity: number | null
  provider: string | null
  model: string | null
  reasoning: string | null
  estimated_llm_calls: number
  outputs_count?: number
  outputs_has_collection?: boolean
}

export interface RunOut {
  id: string
  skill_id: string
  input_doc_id: string | null
  input_doc_ids: string[] | null
  output_doc_id: string | null
  output_doc_ids?: string[] | null
  status: string
  trace: unknown[] | null
  // Raw agent/script output, kept even when persist=false (CATALOG-18).
  result_text: string | null
  result_artifacts?: unknown
  parent_run_id: string | null
}

/** Output mode for applying a skill (CATALOG-18): "в док" vs "на экран". */
export type ApplyMode = 'persist' | 'preview'

export interface SessionCreated {
  id: string
  skipped_doc_ids: string[]
}

export interface SessionOut {
  id: string
  status: string
  created_at: string
  updated_at: string
  title: string | null
  skill_id: string | null
  llm_timeout_seconds: number
}

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, statusText: string, body: string) {
    const detail = parseApiDetailBody(body) || `${status} ${statusText}`
    super(`${status} ${statusText}${body ? `: ${body}` : ''}`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

function parseApiDetailBody(body: string): string | null {
  const trimmed = body.trim()
  if (!trimmed) return null
  try {
    const parsed = JSON.parse(trimmed) as { detail?: unknown }
    return formatApiDetail(parsed.detail)
  } catch {
    return null
  }
}

export function formatApiDetail(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object' && 'msg' in item) {
          const msg = (item as { msg?: unknown }).msg
          return typeof msg === 'string' ? msg : null
        }
        return null
      })
      .filter((x): x is string => !!x && x.trim().length > 0)
    return parts.length > 0 ? parts.join('; ') : null
  }
  if (detail && typeof detail === 'object') {
    const obj = detail as { message?: unknown; msg?: unknown }
    if (typeof obj.message === 'string' && obj.message.trim()) return obj.message
    if (typeof obj.msg === 'string' && obj.msg.trim()) return obj.msg
  }
  return null
}

export function extractApiDetail(e: unknown): string {
  if (e instanceof ApiError) return e.detail
  const msg = e instanceof Error ? e.message : String(e)
  const jsonStart = msg.indexOf('{')
  if (jsonStart >= 0) {
    try {
      const parsed = JSON.parse(msg.slice(jsonStart)) as { detail?: unknown }
      const formatted = formatApiDetail(parsed.detail)
      if (formatted) return formatted
    } catch {}
  }
  return msg
}

export function isBuildTimeoutError(e: unknown, detail?: string): boolean {
  if (e instanceof ApiError && e.status === 504) return true
  const msg = (e instanceof Error ? e.message : String(e)).toLowerCase()
  if (/^504\b/.test(msg) || msg.includes(' 504 ')) return true
  const text = (detail ?? extractApiDetail(e)).toLowerCase()
  return text.includes('timed out') || text.includes('timeout')
}

export interface MessageOut {
  id: number
  session_id: string
  role: string
  content: string | null
  tool_name: string | null
  tool_call_id: string | null
  created_at: string
}

export interface EditStarted {
  session_id: string
  skill_id: string
}

export interface SkillOutputOut {
  key: string
  description: string
  multiple?: boolean
}

export interface SkillPreview {
  name: string
  description: string | null
  kind: string
  model: string
  provider: string
  reasoning: string
  input_arity: number | null
  allowed_tools: string[]
  // CATALOG-155: named outputs declared via set_skill_outputs / the settings
  // modal. Optional on the client: the backend always sends an array, but
  // the client stays tolerant of an absent field and reads it as "no
  // outputs" (same presence semantics as elsewhere, ADR-0024).
  outputs?: SkillOutputOut[]
}

export interface SkillBuilt {
  skill_id: string
  config: SkillPreview
}

export interface ModelOut {
  id: string
  name: string
  context_length: number | null
  supports_reasoning: boolean
  reasoning_variants: string[]
}

export interface ProviderOut {
  id: string
  name: string
  active: boolean
}

export interface CommitOut {
  id: string
  status: string
}

export interface RunCreated {
  run_id: string
}

export interface HealthOut {
  status: string
  git_sha: string
}

const envUrl: string | undefined = import.meta.env.VITE_API_URL
export const API_URL: string =
  envUrl === undefined
    ? import.meta.env.DEV
      ? 'http://localhost:8000'
      : ''
    : envUrl

export function wsBaseUrl(): string {
  if (!API_URL) {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${window.location.host}`
  }
  return API_URL.replace(/^http/, 'ws')
}

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, init)
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new ApiError(res.status, res.statusText, body)
  }
  return (await res.json()) as T
}

export function getHealth(): Promise<HealthOut> {
  return jsonFetch<HealthOut>('/health')
}

export interface WorkspaceOut {
  path: string
  display_name: string | null
  last_opened: string | null
}

export interface ScanReport {
  added: string[]
  updated: string[]
  renamed: string[]
  removed: string[]
  skipped: string[]
}

export type WorkspaceOpenStatus = 'ok' | 'needs_init' | 'needs_confirm'

export interface WorkspaceOpenResult {
  status: WorkspaceOpenStatus
  path: string | null
  display_name: string | null
  scan: ScanReport | null
}

export interface FsEntry {
  name: string
  path: string
  has_catalog: boolean
}

export function listWorkspaces(): Promise<WorkspaceOut[]> {
  return jsonFetch<WorkspaceOut[]>('/workspaces')
}

export async function getCurrentWorkspace(): Promise<WorkspaceOut | null> {
  const res = await fetch(`${API_URL}/workspaces/current`)
  if (res.status === 204) return null
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new ApiError(res.status, res.statusText, body)
  }
  return (await res.json()) as WorkspaceOut
}

export function openWorkspace(
  path: string,
  confirm = false,
): Promise<WorkspaceOpenResult> {
  return jsonFetch<WorkspaceOpenResult>('/workspaces/open', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, confirm }),
  })
}

export function rescanWorkspace(): Promise<ScanReport> {
  return jsonFetch<ScanReport>('/workspaces/rescan', { method: 'POST' })
}

export function browseFs(path?: string): Promise<FsEntry[]> {
  const qs =
    path != null && path !== ''
      ? `?path=${encodeURIComponent(path)}`
      : ''
  return jsonFetch<FsEntry[]>(`/fs/browse${qs}`)
}

export type WorkspaceBusyReason = 'run' | 'session'

export interface WorkspaceBusyOut {
  busy: boolean
  reason: WorkspaceBusyReason | null
}

export function getWorkspaceBusy(): Promise<WorkspaceBusyOut> {
  return jsonFetch<WorkspaceBusyOut>('/workspaces/busy')
}

export function listDocuments(): Promise<DocumentOut[]> {
  return jsonFetch<DocumentOut[]>('/documents')
}

export function uploadDocument(file: File): Promise<DocumentOut> {
  const form = new FormData()
  form.append('file', file)
  return jsonFetch<DocumentOut>('/documents', { method: 'POST', body: form })
}

export interface ExportDocxOut {
  ok: boolean
  path: string
  headings: number
  tables: number
}

export function exportDocx(body: {
  doc_ids: string[]
  title?: string
  template?: string
}): Promise<ExportDocxOut> {
  const payload: { doc_ids: string[]; title?: string; template?: string } = {
    doc_ids: body.doc_ids,
  }
  const title = body.title?.trim()
  if (title) payload.title = title
  const template = body.template?.trim()
  if (template) payload.template = template
  return jsonFetch<ExportDocxOut>('/export/docx', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function createSession(docIds?: string[]): Promise<SessionCreated> {
  if (docIds && docIds.length > 0) {
    return jsonFetch<SessionCreated>('/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ doc_ids: docIds }),
    })
  }
  return jsonFetch<SessionCreated>('/sessions', { method: 'POST' })
}

export function listSessions(params?: {
  limit?: number
  offset?: number
  status?: string
}): Promise<SessionOut[]> {
  const qs = new URLSearchParams()
  if (params?.limit != null) qs.set('limit', String(params.limit))
  if (params?.offset != null) qs.set('offset', String(params.offset))
  if (params?.status) qs.set('status', params.status)
  const q = qs.toString()
  return jsonFetch<SessionOut[]>(`/sessions${q ? `?${q}` : ''}`)
}

export function getSession(sessionId: string): Promise<SessionOut> {
  return jsonFetch<SessionOut>(`/sessions/${sessionId}`)
}

export function updateSessionTimeout(
  sessionId: string,
  llmTimeoutSeconds: number,
): Promise<SessionOut> {
  return jsonFetch<SessionOut>(`/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ llm_timeout_seconds: llmTimeoutSeconds }),
  })
}

export function listSessionMessages(sessionId: string): Promise<MessageOut[]> {
  return jsonFetch<MessageOut[]>(`/sessions/${sessionId}/messages`)
}

export function getSessionDocuments(sessionId: string): Promise<DocumentOut[]> {
  return jsonFetch<DocumentOut[]>(`/sessions/${sessionId}/documents`)
}

export async function removeSessionDocument(
  sessionId: string,
  docId: string,
): Promise<void> {
  const res = await fetch(
    `${API_URL}/sessions/${sessionId}/documents/${docId}`,
    { method: 'DELETE' },
  )
  if (res.status === 204) return
  const body = await res.text().catch(() => '')
  if (res.status === 404 && body.includes('document not attached')) return
  throw new Error(`${res.status} ${res.statusText}${body ? `: ${body}` : ''}`)
}

export interface SessionToolsAttachResult {
  skipped_skill_ids: string[]
  skills: SkillOut[]
}

export function getSessionTools(sessionId: string): Promise<SkillOut[]> {
  return jsonFetch<SkillOut[]>(`/sessions/${sessionId}/tools`)
}

export function attachSessionTools(
  sessionId: string,
  skillIds: string[],
): Promise<SessionToolsAttachResult> {
  return jsonFetch<SessionToolsAttachResult>(`/sessions/${sessionId}/tools`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ skill_ids: skillIds }),
  })
}

export async function removeSessionTool(
  sessionId: string,
  skillId: string,
): Promise<void> {
  const res = await fetch(
    `${API_URL}/sessions/${sessionId}/tools/${skillId}`,
    { method: 'DELETE' },
  )
  if (res.status === 204) return
  const body = await res.text().catch(() => '')
  if (res.status === 404 && body.includes('skill not attached')) return
  throw new ApiError(res.status, res.statusText, body)
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_URL}/sessions/${sessionId}`, { method: 'DELETE' })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}${body ? `: ${body}` : ''}`)
  }
}

export function buildSkill(sessionId: string): Promise<SkillBuilt> {
  return jsonFetch<SkillBuilt>(`/sessions/${sessionId}/skills`, { method: 'POST' })
}

export interface SkillTrack {
  name: string
  description: string
  operation: string
  input_arity: number | null
  rationale: string
}

export interface SkillTracksOut {
  tracks: SkillTrack[]
  skipped: boolean
  fallback: boolean
}

export interface SkillTrackSelected {
  session_id: string
  content: string
}

export function proposeSkillTracks(sessionId: string): Promise<SkillTracksOut> {
  return jsonFetch<SkillTracksOut>(`/sessions/${sessionId}/skill-tracks`, {
    method: 'POST',
  })
}

export function selectSkillTrack(
  sessionId: string,
  track: SkillTrack,
): Promise<SkillTrackSelected> {
  return jsonFetch<SkillTrackSelected>(`/sessions/${sessionId}/skill-tracks/select`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ track }),
  })
}

/** Start an edit session for an existing skill (CATALOG-17). */
export function startEditSession(skillId: string): Promise<EditStarted> {
  return jsonFetch<EditStarted>(`/skills/${skillId}/edit`, { method: 'POST' })
}

export function commitSkill(skillId: string): Promise<CommitOut> {
  return jsonFetch<CommitOut>(`/skills/${skillId}/commit`, { method: 'POST' })
}

export async function deleteSkill(skillId: string): Promise<void> {
  const res = await fetch(`${API_URL}/skills/${skillId}`, { method: 'DELETE' })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}${body ? `: ${body}` : ''}`)
  }
}

export function listSkills(status?: string): Promise<SkillOut[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : ''
  return jsonFetch<SkillOut[]>(`/skills${qs}`)
}

export function applySkill(
  skillId: string,
  docIds: string[],
  mode: ApplyMode = 'persist',
  sessionId?: string | null,
  prompt?: string,
): Promise<RunCreated> {
  const body: {
    doc_ids: string[]
    persist: boolean
    session_id?: string
    prompt?: string
  } = { doc_ids: docIds, persist: mode === 'persist' }
  if (sessionId) body.session_id = sessionId
  const trimmed = prompt?.trim()
  if (trimmed) body.prompt = trimmed
  return jsonFetch<RunCreated>(`/skills/${skillId}/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function getRun(runId: string): Promise<RunOut> {
  return jsonFetch<RunOut>(`/runs/${runId}`)
}

/** Materialize a preview run's on-screen result into a document (CATALOG-18). */
export function saveRunResult(runId: string): Promise<DocumentOut> {
  return jsonFetch<DocumentOut>(`/runs/${runId}/save`, { method: 'POST' })
}

export function listModels(): Promise<ModelOut[]> {
  return jsonFetch<ModelOut[]>('/models')
}

export function listProviders(): Promise<ProviderOut[]> {
  return jsonFetch<ProviderOut[]>('/providers')
}

export function configureSkill(
  skillId: string,
  settings: {
    model?: string
    provider?: string
    reasoning?: string
    input_arity?: number | null
    name?: string
    outputs?: SkillOutputOut[]
  },
): Promise<SkillBuilt> {
  return jsonFetch<SkillBuilt>(`/skills/${skillId}/configure`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  })
}

export function renameSkill(skillId: string, name: string): Promise<SkillOut> {
  return jsonFetch<SkillOut>(`/skills/${skillId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
}

export interface SettingsOut {
  provider: string
  model: string
  keys_configured?: boolean
}

export interface ProviderSetupOut {
  id: string
  name: string
  configured: boolean
  managed_by_env: boolean
  active: boolean
}

export interface SetupOut {
  keys_configured: boolean
  provider: string
  openrouter_configured: boolean
  zai_configured: boolean
  providers: ProviderSetupOut[]
}

export interface SettingsUpdate {
  provider?: string
  model?: string
}

export interface SetupKeysInput {
  openrouter_api_key?: string
  zai_api_key?: string
}

export function getSettings(): Promise<SettingsOut> {
  return jsonFetch<SettingsOut>('/settings')
}

export function getSetup(): Promise<SetupOut> {
  return jsonFetch<SetupOut>('/setup')
}

export function saveProviderKey(input: SetupKeysInput): Promise<SetupOut> {
  return jsonFetch<SetupOut>('/setup/keys', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
}

export function getProviderModels(providerId: string): Promise<ModelOut[]> {
  return jsonFetch<ModelOut[]>(`/providers/${encodeURIComponent(providerId)}/models`)
}

export function updateSettings(settings: SettingsUpdate): Promise<SettingsOut> {
  return jsonFetch<SettingsOut>('/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  })
}

export type ArtifactType = 'prompt' | 'script' | 'meta' | 'steps' | 'outputs'

export type SkillKind = 'agent' | 'script' | 'pipeline'

export type PipelineStepType = 'script' | 'llm' | 'skill'

export type PipelineStepInput = 'documents' | 'previous'

export interface PipelineStepDraft {
  id: string
  type: PipelineStepType
  input: PipelineStepInput
  code: string
  system_prompt: string
  allowed_tools: string[]
  model: string
  provider: string
  reasoning: string
  skill_id: string
  skill_name: string
  config_hash: string
  skill_kind: string
}

export function parseStepsArtifact(content: string): {
  steps: PipelineStepDraft[]
  parseError: string | null
} {
  const trimmed = content.trim()
  if (!trimmed) return { steps: [], parseError: null }
  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch {
    return { steps: [], parseError: 'steps must be JSON' }
  }
  let rawList: unknown
  if (Array.isArray(parsed)) {
    rawList = parsed
  } else if (parsed && typeof parsed === 'object') {
    const obj = parsed as Record<string, unknown>
    if ('steps' in obj) {
      rawList = obj.steps
    } else {
      return { steps: [], parseError: 'steps must be a list' }
    }
  } else {
    return { steps: [], parseError: 'steps must be a list' }
  }
  if (!Array.isArray(rawList)) {
    return { steps: [], parseError: 'steps must be a list' }
  }
  const steps: PipelineStepDraft[] = []
  for (let i = 0; i < rawList.length; i++) {
    const item = rawList[i]
    if (!item || typeof item !== 'object' || Array.isArray(item)) continue
    steps.push(normalizePipelineStep(item as Record<string, unknown>, i))
  }
  return { steps, parseError: null }
}

export const OUTPUT_KEY_RE = /^[a-z][a-z0-9_]{0,31}$/

export const MAX_SKILL_OUTPUTS = 8

export interface OutputDraft {
  key: string
  description: string
  multiple?: boolean
}

export interface OutputRowError {
  key?: string
  description?: string
  multiple?: string
}

export interface RunArtifact {
  key: string
  description?: string | null
  text: string | string[]
}

const OUTPUT_MULTIPLE_TYPE_ERROR = 'несколько документов: только true или false'

export function parseOutputsArtifact(content: string): {
  outputs: OutputDraft[]
  parseError: string | null
  rowErrors: (OutputRowError | null)[]
} {
  const trimmed = content.trim()
  if (!trimmed) return { outputs: [], parseError: null, rowErrors: [] }
  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch {
    return { outputs: [], parseError: 'outputs must be JSON', rowErrors: [] }
  }
  if (!Array.isArray(parsed)) {
    return { outputs: [], parseError: 'outputs must be a JSON array', rowErrors: [] }
  }
  const outputs: OutputDraft[] = []
  const rowErrors: (OutputRowError | null)[] = []
  for (const item of parsed) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) continue
    const rec = item as Record<string, unknown>
    const draft: OutputDraft = {
      key: typeof rec.key === 'string' ? rec.key : '',
      description: typeof rec.description === 'string' ? rec.description : '',
    }
    let rowError: OutputRowError | null = null
    if ('multiple' in rec) {
      if (typeof rec.multiple === 'boolean') {
        draft.multiple = rec.multiple
      } else {
        rowError = { multiple: OUTPUT_MULTIPLE_TYPE_ERROR }
      }
    }
    outputs.push(draft)
    rowErrors.push(rowError)
  }
  return { outputs, parseError: null, rowErrors }
}

/** Single normalization point for outputs sent to the backend (CATALOG-155):
 * key/description trimmed, `multiple` present only when `true`, order kept
 * 1:1 with the input array. Used by both `serializeOutputs` (artifact card)
 * and `configureSkill` callers (settings modal). */
export function outputsPayload(outputs: OutputDraft[]): SkillOutputOut[] {
  return outputs.map((item) => {
    const out: SkillOutputOut = {
      key: item.key.trim(),
      description: item.description.trim(),
    }
    if (item.multiple === true) out.multiple = true
    return out
  })
}

export function serializeOutputs(outputs: OutputDraft[]): string {
  return JSON.stringify(outputsPayload(outputs))
}

export function validateOutputs(outputs: OutputDraft[]): {
  ok: boolean
  rowErrors: (OutputRowError | null)[]
} {
  const rowErrors: (OutputRowError | null)[] = outputs.map(() => null)
  const seen = new Set<string>()
  for (let i = 0; i < outputs.length; i++) {
    const key = outputs[i].key.trim()
    const description = outputs[i].description.trim()
    const err: OutputRowError = {}
    if (!key || !OUTPUT_KEY_RE.test(key)) {
      err.key = 'ключ: только a-z, цифры и _'
    } else if (seen.has(key)) {
      err.key = 'такой ключ уже есть'
    } else {
      seen.add(key)
    }
    if (!description) {
      err.description = 'описание не может быть пустым'
    }
    const multiple = outputs[i].multiple
    if (multiple !== undefined && typeof multiple !== 'boolean') {
      err.multiple = OUTPUT_MULTIPLE_TYPE_ERROR
    }
    if (err.key || err.description || err.multiple) rowErrors[i] = err
  }
  return { ok: rowErrors.every((item) => item == null), rowErrors }
}

export function normalizeRunArtifacts(raw: unknown): RunArtifact[] {
  if (Array.isArray(raw)) {
    const out: RunArtifact[] = []
    for (const item of raw) {
      if (!item || typeof item !== 'object' || Array.isArray(item)) continue
      const rec = item as Record<string, unknown>
      if (typeof rec.key !== 'string') continue
      let text: string | string[] | null = null
      if (typeof rec.text === 'string') {
        text = rec.text
      } else if (Array.isArray(rec.text)) {
        text = rec.text.filter((el): el is string => typeof el === 'string')
      }
      if (text === null) continue
      const description =
        typeof rec.description === 'string'
          ? rec.description
          : rec.description === null
            ? null
            : undefined
      out.push({ key: rec.key, text, description })
    }
    return out
  }
  if (raw && typeof raw === 'object') {
    const out: RunArtifact[] = []
    for (const [key, text] of Object.entries(raw as Record<string, unknown>)) {
      if (typeof text === 'string') {
        out.push({ key, text })
      } else if (Array.isArray(text)) {
        out.push({ key, text: text.filter((el): el is string => typeof el === 'string') })
      }
    }
    return out
  }
  return []
}

function normalizePipelineStep(
  data: Record<string, unknown>,
  index: number,
): PipelineStepDraft {
  const rawType = typeof data.type === 'string' ? data.type.trim().toLowerCase() : ''
  const rawInput = typeof data.input === 'string' ? data.input : ''
  const rawTools = data.allowed_tools
  const tools = Array.isArray(rawTools) ? rawTools.map(String) : []
  const prompt =
    typeof data.system_prompt === 'string' && data.system_prompt
      ? data.system_prompt
      : typeof data.prompt === 'string'
        ? data.prompt
        : ''
  const config =
    data.config && typeof data.config === 'object' && !Array.isArray(data.config)
      ? (data.config as Record<string, unknown>)
      : null
  const skillKind = typeof config?.kind === 'string' ? config.kind : ''
  return {
    id: typeof data.id === 'string' ? data.id : '',
    type: rawType === 'llm' ? 'llm' : rawType === 'skill' ? 'skill' : 'script',
    input:
      rawInput === 'documents' || rawInput === 'previous'
        ? rawInput
        : index === 0
          ? 'documents'
          : 'previous',
    code: typeof data.code === 'string' ? data.code : '',
    system_prompt: prompt,
    allowed_tools: tools,
    model: typeof data.model === 'string' ? data.model : '',
    provider: typeof data.provider === 'string' ? data.provider : '',
    reasoning: typeof data.reasoning === 'string' ? data.reasoning : '',
    skill_id: typeof data.skill_id === 'string' ? data.skill_id : '',
    skill_name: typeof data.skill_name === 'string' ? data.skill_name : '',
    config_hash: typeof data.config_hash === 'string' ? data.config_hash : '',
    skill_kind: skillKind,
  }
}

export type ScriptDryRunStage = 'validate' | 'run' | 'verify'

export interface ScriptDryRunStatus {
  slot: string
  sha256: string
  ok: boolean
  stage: ScriptDryRunStage | null
  error: string | null
  time: string | null
}

export interface ScriptTryVerifyCheck {
  check: string
  params?: Record<string, unknown>
  passed: boolean
  reason: string | null
  source: string
  skipped: boolean
}

export interface ScriptTryVerify {
  passed: boolean
  failures: string[]
  checks: ScriptTryVerifyCheck[]
}

export interface ScriptTryResult {
  ok: boolean
  stage: ScriptDryRunStage | null
  error: string | null
  input_preview: string
  input_len: number
  output_preview: string
  output_len: number
  output_kind: 'str' | 'list' | 'dict' | null
  duration_ms: number
  verify: ScriptTryVerify | null
  line_no: number | null
  source_line: string | null
}

export interface ScriptTryRequest {
  code?: string | null
  doc_ids?: string[] | null
  step_index?: number | null
}

export interface SessionArtifact {
  type: ArtifactType
  content: string
  is_valid: boolean
  error: string | null
  source: string
  updated_at: string
  dry_run?: ScriptDryRunStatus | ScriptDryRunStatus[] | null
}

export interface SkillMetaPatch {
  name: string
  description: string
  kind: string
  input_arity: number | null
  allowed_tools: string[]
  verify_checks: { check: string; params?: Record<string, unknown> }[]
}

export interface VerifyChecksCatalog {
  builtin: string[]
  labels: Record<string, string>
}

export interface CustomCheckOut {
  id: string
  name: string
  prompt: string
  hidden: boolean
  created_at: string
}

export interface CustomCheckPreviewOut {
  passed: boolean
  failures: string[]
}

export function listVerifyCheckCatalog(): Promise<VerifyChecksCatalog> {
  return jsonFetch<VerifyChecksCatalog>('/verify-checks')
}

export function listCustomChecks(): Promise<CustomCheckOut[]> {
  return jsonFetch<CustomCheckOut[]>('/custom-checks')
}

export function createCustomCheck(body: {
  name: string
  prompt: string
}): Promise<CustomCheckOut> {
  return jsonFetch<CustomCheckOut>('/custom-checks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function previewCustomCheck(body: {
  prompt: string
  sample: string
}): Promise<CustomCheckPreviewOut> {
  return jsonFetch<CustomCheckPreviewOut>('/custom-checks/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function hideCustomCheck(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/custom-checks/${encodeURIComponent(id)}/hide`, {
    method: 'POST',
  })
  if (res.status === 204) return
  const body = await res.text().catch(() => '')
  throw new ApiError(res.status, res.statusText, body)
}

export function getSessionArtifacts(sessionId: string): Promise<SessionArtifact[]> {
  return jsonFetch<SessionArtifact[]>(`/sessions/${sessionId}/artifacts`)
}

export function trySkillScript(
  sessionId: string,
  body?: ScriptTryRequest,
): Promise<ScriptTryResult> {
  return jsonFetch<ScriptTryResult>(`/sessions/${sessionId}/artifacts/script/try`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
}

export function patchArtifact(
  sessionId: string,
  type: ArtifactType,
  content: string,
): Promise<SessionArtifact> {
  return jsonFetch<SessionArtifact>(`/sessions/${sessionId}/artifacts/${type}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
}

export function patchSkillMeta(
  sessionId: string,
  meta: SkillMetaPatch,
): Promise<SessionArtifact> {
  return jsonFetch<SessionArtifact>(`/sessions/${sessionId}/skill-meta`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(meta),
  })
}
