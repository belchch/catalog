import { useEffect, useRef, useState, type ReactNode } from 'react'
import type {
  ArtifactType,
  SessionArtifact,
  SkillMetaPatch,
} from '../api.ts'

type InputArity = 1 | 2 | null
type SkillKind = 'agent' | 'script'
type SectionSaving = ArtifactType | null

interface MetaDraft {
  name: string
  description: string
  kind: SkillKind
  inputArity: InputArity
  allowedTools: string
  verifyChecks: string
}

interface ArtifactsPanelProps {
  sessionId: string | null
  artifacts: SessionArtifact[]
  loading: boolean
  error: string | null
  streaming: boolean
  highlightType: ArtifactType | null
  onClearHighlight: () => void
  onSavePrompt: (content: string) => Promise<SessionArtifact>
  onSaveScript: (content: string) => Promise<SessionArtifact>
  onSaveMeta: (meta: SkillMetaPatch) => Promise<SessionArtifact>
}

const ARITY_OPTIONS: { value: InputArity; label: string }[] = [
  { value: 1, label: '1 документ' },
  { value: 2, label: '2 документа' },
  { value: null, label: 'Список' },
]

const KIND_OPTIONS: { value: SkillKind; label: string }[] = [
  { value: 'agent', label: 'agent' },
  { value: 'script', label: 'script' },
]

const EMPTY_META: MetaDraft = {
  name: '',
  description: '',
  kind: 'agent',
  inputArity: 1,
  allowedTools: '',
  verifyChecks: '',
}

const fieldCls = 'w-full rounded bg-slate-800 px-2 py-1 text-xs text-slate-100'

function findArtifact(
  artifacts: SessionArtifact[],
  type: ArtifactType,
): SessionArtifact | undefined {
  return artifacts.find((a) => a.type === type)
}

function parseMetaContent(content: string): MetaDraft {
  if (!content.trim()) return { ...EMPTY_META }
  try {
    const parsed = JSON.parse(content) as Record<string, unknown>
    const kind = parsed.kind === 'script' ? 'script' : 'agent'
    const arityRaw = parsed.input_arity
    const inputArity: InputArity =
      arityRaw === 1 || arityRaw === 2 || arityRaw === null ? arityRaw : 1
    const tools = Array.isArray(parsed.allowed_tools)
      ? (parsed.allowed_tools as unknown[]).map(String).join(', ')
      : ''
    const checks = Array.isArray(parsed.verify_checks)
      ? (parsed.verify_checks as unknown[])
          .map((c) =>
            c && typeof c === 'object' && 'check' in c
              ? String((c as { check: unknown }).check)
              : '',
          )
          .filter(Boolean)
          .join(', ')
      : ''
    return {
      name: typeof parsed.name === 'string' ? parsed.name : '',
      description: typeof parsed.description === 'string' ? parsed.description : '',
      kind,
      inputArity,
      allowedTools: tools,
      verifyChecks: checks,
    }
  } catch {
    return { ...EMPTY_META }
  }
}

function metaToPatch(draft: MetaDraft): SkillMetaPatch {
  const tools = draft.allowedTools
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
  const checks = draft.verifyChecks
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
    .map((check) => ({ check }))
  return {
    name: draft.name.trim(),
    description: draft.description,
    kind: draft.kind,
    input_arity: draft.inputArity,
    allowed_tools: draft.kind === 'script' ? [] : tools,
    verify_checks: checks,
  }
}

function metaSnapshot(draft: MetaDraft): string {
  return JSON.stringify(metaToPatch(draft))
}

function formatUpdatedAt(iso: string): string {
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleString()
  } catch {
    return iso
  }
}

function cycleOption<T>(options: { value: T }[], current: T, dir: 1 | -1): T {
  const idx = options.findIndex((o) => o.value === current)
  const next = (idx + dir + options.length) % options.length
  return options[next].value
}

export function ArtifactsPanel({
  sessionId,
  artifacts,
  loading,
  error,
  streaming,
  highlightType,
  onClearHighlight,
  onSavePrompt,
  onSaveScript,
  onSaveMeta,
}: ArtifactsPanelProps) {
  const [promptDraft, setPromptDraft] = useState('')
  const [scriptDraft, setScriptDraft] = useState('')
  const [metaDraft, setMetaDraft] = useState<MetaDraft>({ ...EMPTY_META })
  const [serverPrompt, setServerPrompt] = useState('')
  const [serverScript, setServerScript] = useState('')
  const [serverMetaSnap, setServerMetaSnap] = useState(metaSnapshot(EMPTY_META))
  const [saving, setSaving] = useState<SectionSaving>(null)
  const [saveErrors, setSaveErrors] = useState<Partial<Record<ArtifactType, string>>>({})
  const [savedFlash, setSavedFlash] = useState<Partial<Record<ArtifactType, boolean>>>({})
  const [nameClientError, setNameClientError] = useState(false)

  const metaRef = useRef<HTMLDivElement>(null)
  const promptRef = useRef<HTMLTextAreaElement>(null)
  const scriptRef = useRef<HTMLTextAreaElement>(null)
  const nameRef = useRef<HTMLInputElement>(null)
  const dirtyRef = useRef({ meta: false, prompt: false, script: false })
  const flashTimers = useRef<Partial<Record<ArtifactType, ReturnType<typeof setTimeout>>>>({})

  const promptArt = findArtifact(artifacts, 'prompt')
  const scriptArt = findArtifact(artifacts, 'script')
  const metaArt = findArtifact(artifacts, 'meta')

  const dirtyMeta = metaSnapshot(metaDraft) !== serverMetaSnap
  const dirtyPrompt = promptDraft !== serverPrompt
  const dirtyScript = scriptDraft !== serverScript
  dirtyRef.current = { meta: dirtyMeta, prompt: dirtyPrompt, script: dirtyScript }

  useEffect(() => {
    setPromptDraft('')
    setScriptDraft('')
    setMetaDraft({ ...EMPTY_META })
    setServerPrompt('')
    setServerScript('')
    setServerMetaSnap(metaSnapshot(EMPTY_META))
    setSaving(null)
    setSaveErrors({})
    setSavedFlash({})
    setNameClientError(false)
  }, [sessionId])

  useEffect(() => {
    const dirty = dirtyRef.current
    if (!dirty.prompt) {
      const content = promptArt?.content ?? ''
      setPromptDraft(content)
      setServerPrompt(content)
    } else if (promptArt) {
      setServerPrompt(promptArt.content)
    }
    if (!dirty.script) {
      const content = scriptArt?.content ?? ''
      setScriptDraft(content)
      setServerScript(content)
    } else if (scriptArt) {
      setServerScript(scriptArt.content)
    }
    if (!dirty.meta) {
      const parsed = parseMetaContent(metaArt?.content ?? '')
      setMetaDraft(parsed)
      setServerMetaSnap(metaSnapshot(parsed))
    } else if (metaArt) {
      setServerMetaSnap(metaSnapshot(parseMetaContent(metaArt.content)))
    }
  }, [artifacts, promptArt, scriptArt, metaArt])

  useEffect(() => {
    if (!highlightType) return
    const el =
      highlightType === 'meta'
        ? nameRef.current
        : highlightType === 'prompt'
          ? promptRef.current
          : scriptRef.current
    const section =
      highlightType === 'meta'
        ? metaRef.current
        : highlightType === 'prompt'
          ? promptRef.current
          : scriptRef.current
    section?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    el?.focus()
  }, [highlightType, sessionId])

  useEffect(() => {
    const timers = flashTimers.current
    return () => {
      for (const t of Object.values(timers)) {
        if (t) clearTimeout(t)
      }
    }
  }, [])

  const inputsDisabled = streaming

  const kind = metaDraft.kind
  const hasMeta = Boolean(metaArt?.content.trim())

  const flashSaved = (type: ArtifactType) => {
    setSavedFlash((prev) => ({ ...prev, [type]: true }))
    if (flashTimers.current[type]) clearTimeout(flashTimers.current[type])
    flashTimers.current[type] = setTimeout(() => {
      setSavedFlash((prev) => ({ ...prev, [type]: false }))
    }, 1500)
  }

  const clearHighlightIf = (type: ArtifactType) => {
    if (highlightType === type) onClearHighlight()
  }

  const handleSaveMeta = async () => {
    if (streaming || saving === 'meta') return
    if (!metaDraft.name.trim()) {
      setNameClientError(true)
      return
    }
    setNameClientError(false)
    setSaving('meta')
    setSaveErrors((prev) => ({ ...prev, meta: undefined }))
    try {
      const art = await onSaveMeta(metaToPatch(metaDraft))
      const parsed = parseMetaContent(art.content)
      setMetaDraft(parsed)
      setServerMetaSnap(metaSnapshot(parsed))
      flashSaved('meta')
      clearHighlightIf('meta')
    } catch (e) {
      setSaveErrors((prev) => ({
        ...prev,
        meta: e instanceof Error ? e.message : String(e),
      }))
    } finally {
      setSaving(null)
    }
  }

  const handleSavePrompt = async () => {
    if (streaming || saving === 'prompt') return
    setSaving('prompt')
    setSaveErrors((prev) => ({ ...prev, prompt: undefined }))
    try {
      const art = await onSavePrompt(promptDraft)
      setPromptDraft(art.content)
      setServerPrompt(art.content)
      flashSaved('prompt')
      clearHighlightIf('prompt')
    } catch (e) {
      setSaveErrors((prev) => ({
        ...prev,
        prompt: e instanceof Error ? e.message : String(e),
      }))
    } finally {
      setSaving(null)
    }
  }

  const handleSaveScript = async () => {
    if (streaming || saving === 'script') return
    setSaving('script')
    setSaveErrors((prev) => ({ ...prev, script: undefined }))
    try {
      const art = await onSaveScript(scriptDraft)
      setScriptDraft(art.content)
      setServerScript(art.content)
      flashSaved('script')
      clearHighlightIf('script')
    } catch (e) {
      setSaveErrors((prev) => ({
        ...prev,
        script: e instanceof Error ? e.message : String(e),
      }))
    } finally {
      setSaving(null)
    }
  }

  const emptyArtifacts = artifacts.length === 0 && !loading

  const sectionShell = (
    type: ArtifactType,
    invalid: boolean,
    children: ReactNode,
  ) => {
    const highlighted = highlightType === type
    return (
      <div
        ref={type === 'meta' ? metaRef : undefined}
        className={
          'rounded-md border bg-slate-900/50 p-3 ' +
          (invalid ? 'border-red-500/50 ' : 'border-slate-800 ') +
          (highlighted ? 'ring-1 ring-red-400/60 ' : '') +
          (type === 'prompt' && hasMeta && kind === 'script' ? 'opacity-70 ' : '') +
          (type === 'script' && hasMeta && kind === 'agent' ? 'opacity-70 ' : '')
        }
      >
        {children}
      </div>
    )
  }

  const statusRow = (art: SessionArtifact | undefined) => (
    <span className="text-[10px] text-slate-500">
      {art ? `${art.source} · ${formatUpdatedAt(art.updated_at)}` : '—'}
    </span>
  )

  const saveBtn = (
    type: ArtifactType,
    label: string,
    onClick: () => void,
    disabled: boolean,
  ) => (
    <div className="mt-2">
      <div className="flex items-center justify-end gap-2">
        {savedFlash[type] && (
          <span className="text-[10px] text-emerald-400">Сохранено</span>
        )}
        <button
          type="button"
          className="rounded bg-indigo-600 px-3 py-1 text-xs text-white disabled:opacity-50"
          disabled={disabled || inputsDisabled || saving === type}
          onClick={() => void onClick()}
        >
          {saving === type ? 'Сохраняю…' : label}
        </button>
      </div>
      {saveErrors[type] && (
        <p id={`${type}-save-error`} className="mt-1 text-xs text-red-400">
          {saveErrors[type]}
        </p>
      )}
    </div>
  )

  if (!sessionId) {
    return (
      <div
        role="region"
        aria-label="Черновик скилла"
        className="flex h-full flex-col border-l border-slate-800 bg-slate-950"
      >
        <div className="flex flex-1 items-center justify-center p-4 text-center text-sm text-slate-500">
          Выберите сессию или начните новый чат — здесь появится черновик скилла.
        </div>
      </div>
    )
  }

  return (
    <div
      role="region"
      aria-label="Черновик скилла"
      className="flex h-full flex-col border-l border-slate-800 bg-slate-950"
    >
      <div className="flex h-full flex-col gap-3 overflow-y-auto p-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-200">Черновик скилла</h2>
          {streaming && (
            <span className="text-[10px] text-amber-400">планировщик пишет…</span>
          )}
        </div>

        {error && (
          <p className="text-xs text-red-400">{error}</p>
        )}

        {loading && (
          <p className="text-xs text-slate-500">Загружаю артефакты…</p>
        )}

        {emptyArtifacts && !loading && (
          <p className="text-[11px] text-slate-500">
            Планировщик сохранит черновик инструментами, или заполните вручную.
          </p>
        )}

        {sectionShell('meta', metaArt?.is_valid === false || nameClientError, (
          <>
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="text-[11px] uppercase tracking-wide text-slate-500">Meta</h3>
              {statusRow(metaArt)}
            </div>
            <label className="mb-2 block text-[11px] text-slate-400">
              Имя
              <input
                ref={nameRef}
                type="text"
                className={`mt-1 ${fieldCls} disabled:opacity-50`}
                value={metaDraft.name}
                aria-invalid={nameClientError || metaArt?.is_valid === false}
                aria-describedby={
                  [
                    nameClientError || metaArt?.error ? 'meta-error' : null,
                    saveErrors.meta ? 'meta-save-error' : null,
                  ]
                    .filter(Boolean)
                    .join(' ') || undefined
                }
                disabled={inputsDisabled}
                onChange={(e) => {
                  setMetaDraft((d) => ({ ...d, name: e.target.value }))
                  setNameClientError(false)
                  clearHighlightIf('meta')
                }}
              />
            </label>
            <label className="mb-2 block text-[11px] text-slate-400">
              Описание
              <textarea
                className={`mt-1 min-h-[3.5rem] ${fieldCls} disabled:opacity-50`}
                rows={3}
                value={metaDraft.description}
                disabled={inputsDisabled}
                onChange={(e) => {
                  setMetaDraft((d) => ({ ...d, description: e.target.value }))
                  clearHighlightIf('meta')
                }}
              />
            </label>
            <div className="mb-2">
              <div className="mb-1 text-[11px] text-slate-400">Kind</div>
              <div
                role="radiogroup"
                aria-label="Kind"
                className={`flex flex-wrap gap-1 ${inputsDisabled ? 'opacity-50' : ''}`}
                onKeyDown={(e) => {
                  if (inputsDisabled) return
                  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
                    e.preventDefault()
                    setMetaDraft((d) => ({
                      ...d,
                      kind: cycleOption(KIND_OPTIONS, d.kind, 1),
                    }))
                    clearHighlightIf('meta')
                  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
                    e.preventDefault()
                    setMetaDraft((d) => ({
                      ...d,
                      kind: cycleOption(KIND_OPTIONS, d.kind, -1),
                    }))
                    clearHighlightIf('meta')
                  }
                }}
              >
                {KIND_OPTIONS.map((opt) => {
                  const active = metaDraft.kind === opt.value
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      role="radio"
                      aria-checked={active}
                      tabIndex={inputsDisabled ? -1 : active ? 0 : -1}
                      disabled={inputsDisabled}
                      className={
                        'rounded px-2 py-1 text-[11px] disabled:opacity-50 ' +
                        (active
                          ? 'bg-indigo-600 text-white'
                          : 'bg-slate-800 text-slate-300 hover:bg-slate-700')
                      }
                      onClick={() => {
                        setMetaDraft((d) => ({ ...d, kind: opt.value }))
                        clearHighlightIf('meta')
                      }}
                    >
                      {opt.label}
                    </button>
                  )
                })}
              </div>
            </div>
            <div className="mb-2">
              <div className="mb-1 text-[11px] text-slate-400">Вход</div>
              <div
                role="radiogroup"
                aria-label="Вход"
                className={`flex flex-wrap gap-1 ${inputsDisabled ? 'opacity-50' : ''}`}
                onKeyDown={(e) => {
                  if (inputsDisabled) return
                  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
                    e.preventDefault()
                    setMetaDraft((d) => ({
                      ...d,
                      inputArity: cycleOption(ARITY_OPTIONS, d.inputArity, 1),
                    }))
                    clearHighlightIf('meta')
                  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
                    e.preventDefault()
                    setMetaDraft((d) => ({
                      ...d,
                      inputArity: cycleOption(ARITY_OPTIONS, d.inputArity, -1),
                    }))
                    clearHighlightIf('meta')
                  }
                }}
              >
                {ARITY_OPTIONS.map((opt) => {
                  const active = metaDraft.inputArity === opt.value
                  return (
                    <button
                      key={String(opt.value)}
                      type="button"
                      role="radio"
                      aria-checked={active}
                      tabIndex={inputsDisabled ? -1 : active ? 0 : -1}
                      disabled={inputsDisabled}
                      className={
                        'rounded px-2 py-1 text-[11px] disabled:opacity-50 ' +
                        (active
                          ? 'bg-indigo-600 text-white'
                          : 'bg-slate-800 text-slate-300 hover:bg-slate-700')
                      }
                      onClick={() => {
                        setMetaDraft((d) => ({ ...d, inputArity: opt.value }))
                        clearHighlightIf('meta')
                      }}
                    >
                      {opt.label}
                    </button>
                  )
                })}
              </div>
            </div>
            <label className="mb-2 block text-[11px] text-slate-400">
              allowed_tools
              <input
                type="text"
                className={`mt-1 ${fieldCls} disabled:opacity-50`}
                value={metaDraft.allowedTools}
                disabled={inputsDisabled || metaDraft.kind === 'script'}
                placeholder="tool1, tool2"
                onChange={(e) => {
                  setMetaDraft((d) => ({ ...d, allowedTools: e.target.value }))
                  clearHighlightIf('meta')
                }}
              />
              {metaDraft.kind === 'script' && (
                <span className="mt-1 block text-[10px] text-slate-500">
                  не используется для script
                </span>
              )}
            </label>
            <label className="mb-1 block text-[11px] text-slate-400">
              verify_checks
              <input
                type="text"
                className={`mt-1 ${fieldCls} disabled:opacity-50`}
                value={metaDraft.verifyChecks}
                disabled={inputsDisabled}
                placeholder="non_empty, markdown_well_formed"
                onChange={(e) => {
                  setMetaDraft((d) => ({ ...d, verifyChecks: e.target.value }))
                  clearHighlightIf('meta')
                }}
              />
            </label>
            {(nameClientError || metaArt?.error) && (
              <p id="meta-error" className="mt-1 text-[11px] text-red-400">
                {nameClientError ? 'Имя не может быть пустым' : metaArt?.error}
              </p>
            )}
            {saveBtn(
              'meta',
              'Сохранить meta',
              () => void handleSaveMeta(),
              !dirtyMeta,
            )}
          </>
        ))}

        {sectionShell('prompt', promptArt?.is_valid === false, (
          <>
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="text-[11px] uppercase tracking-wide text-slate-500">Prompt</h3>
              {statusRow(promptArt)}
            </div>
            {hasMeta && kind === 'script' && (
              <p className="mb-1 text-[10px] text-slate-500">
                нужен только для kind=agent
              </p>
            )}
            <textarea
              ref={promptRef}
              className={`min-h-[8rem] ${fieldCls} disabled:opacity-50`}
              placeholder="System prompt скилла…"
              value={promptDraft}
              disabled={inputsDisabled}
              aria-invalid={promptArt?.is_valid === false}
              aria-describedby={
                [
                  promptArt?.error ? 'prompt-error' : null,
                  saveErrors.prompt ? 'prompt-save-error' : null,
                ]
                  .filter(Boolean)
                  .join(' ') || undefined
              }
              onChange={(e) => {
                setPromptDraft(e.target.value)
                clearHighlightIf('prompt')
              }}
            />
            {promptArt?.error && (
              <p id="prompt-error" className="mt-1 text-[11px] text-red-400">
                {promptArt.error}
              </p>
            )}
            {saveBtn(
              'prompt',
              'Сохранить prompt',
              () => void handleSavePrompt(),
              !dirtyPrompt,
            )}
          </>
        ))}

        {sectionShell('script', scriptArt?.is_valid === false, (
          <>
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="text-[11px] uppercase tracking-wide text-slate-500">Script</h3>
              {statusRow(scriptArt)}
            </div>
            {hasMeta && kind === 'agent' && (
              <p className="mb-1 text-[10px] text-slate-500">
                нужен только для kind=script
              </p>
            )}
            <textarea
              ref={scriptRef}
              className={`min-h-[10rem] font-mono text-xs leading-relaxed ${fieldCls} disabled:opacity-50`}
              placeholder="Python-скрипт скилла…"
              value={scriptDraft}
              disabled={inputsDisabled}
              aria-invalid={scriptArt?.is_valid === false}
              aria-describedby={
                [
                  scriptArt?.error ? 'script-error' : null,
                  saveErrors.script ? 'script-save-error' : null,
                ]
                  .filter(Boolean)
                  .join(' ') || undefined
              }
              onChange={(e) => {
                setScriptDraft(e.target.value)
                clearHighlightIf('script')
              }}
            />
            {scriptArt?.error && (
              <p id="script-error" className="mt-1 text-[11px] text-red-400">
                {scriptArt.error}
              </p>
            )}
            {saveBtn(
              'script',
              'Сохранить script',
              () => void handleSaveScript(),
              !dirtyScript,
            )}
          </>
        ))}
      </div>
    </div>
  )
}
