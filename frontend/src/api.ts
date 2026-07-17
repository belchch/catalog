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
    throw new Error(`${res.status} ${res.statusText}${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as T
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

export function buildSkill(sessionId: string): Promise<SkillBuilt> {
  return jsonFetch<SkillBuilt>(`/sessions/${sessionId}/skills`, { method: 'POST' })
}

/** Start an edit session for an existing skill (CATALOG-17). */
export function startEditSession(skillId: string): Promise<EditStarted> {
  return jsonFetch<EditStarted>(`/skills/${skillId}/edit`, { method: 'POST' })
}

export function commitSkill(skillId: string): Promise<CommitOut> {
  return jsonFetch<CommitOut>(`/skills/${skillId}/commit`, { method: 'POST' })
}

export function listSkills(status?: string): Promise<SkillOut[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : ''
  return jsonFetch<SkillOut[]>(`/skills${qs}`)
}

export function applySkill(
  skillId: string,
  docIds: string[],
  mode: ApplyMode = 'persist',
): Promise<RunCreated> {
  return jsonFetch<RunCreated>(`/skills/${skillId}/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ doc_ids: docIds, persist: mode === 'persist' }),
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
  settings: { model?: string; provider?: string; reasoning?: string },
): Promise<SkillBuilt> {
  return jsonFetch<SkillBuilt>(`/skills/${skillId}/configure`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
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
