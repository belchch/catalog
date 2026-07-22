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
}

export interface RunOut {
  id: string
  skill_id: string
  input_doc_id: string | null
  input_doc_ids: string[] | null
  output_doc_id: string | null
  status: string
  trace: unknown[] | null
  // Raw agent/script output, kept even when persist=false (CATALOG-18).
  result_text: string | null
}

/** Output mode for applying a skill (CATALOG-18): "в док" vs "на экран". */
export type ApplyMode = 'persist' | 'preview'

export interface SessionCreated {
  id: string
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

export interface SkillPreview {
  name: string
  description: string | null
  kind: string
  model: string
  provider: string
  reasoning: string
  input_arity: number | null
  allowed_tools: string[]
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
  envUrl && envUrl.length > 0 ? envUrl : 'http://localhost:8000'

/** WebSocket base URL derived from the API base (http -> ws, https -> wss). */
export function wsBaseUrl(): string {
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

export function listDocuments(): Promise<DocumentOut[]> {
  return jsonFetch<DocumentOut[]>('/documents')
}

export function uploadDocument(file: File): Promise<DocumentOut> {
  const form = new FormData()
  form.append('file', file)
  return jsonFetch<DocumentOut>('/documents', { method: 'POST', body: form })
}

export function createSession(): Promise<SessionCreated> {
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
}

export function getSettings(): Promise<SettingsOut> {
  return jsonFetch<SettingsOut>('/settings')
}

export function getProviderModels(providerId: string): Promise<ModelOut[]> {
  return jsonFetch<ModelOut[]>(`/providers/${encodeURIComponent(providerId)}/models`)
}

export function updateSettings(settings: SettingsOut): Promise<SettingsOut> {
  return jsonFetch<SettingsOut>('/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  })
}

export type ArtifactType = 'prompt' | 'script' | 'meta'

export interface SessionArtifact {
  type: ArtifactType
  content: string
  is_valid: boolean
  error: string | null
  source: string
  updated_at: string
}

export interface SkillMetaPatch {
  name: string
  description: string
  kind: string
  input_arity: number | null
  allowed_tools: string[]
  verify_checks: { check: string }[]
}

export function getSessionArtifacts(sessionId: string): Promise<SessionArtifact[]> {
  return jsonFetch<SessionArtifact[]>(`/sessions/${sessionId}/artifacts`)
}

export function patchArtifact(
  sessionId: string,
  type: 'prompt' | 'script' | 'meta',
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
