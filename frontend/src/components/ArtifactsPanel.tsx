import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import {
  extractApiDetail,
  parseStepsArtifact,
  type ArtifactType,
  type PipelineStepDraft,
  type ScriptTryResult,
  type SessionArtifact,
  type SkillKind,
  type SkillMetaPatch,
} from '../api.ts'
import {
  dryRunBadgeClass,
  dryRunLabel,
  dryRunState,
  errorLineNo,
  errorSourceLine,
  scriptDryRun,
  stageLabel,
} from '../lib/dryRun.ts'
import { StepsList } from './StepsList.tsx'
import { VerifyChecksPicker, type VerifyCheckDraft } from './VerifyChecksPicker.tsx'

type InputArity = 1 | 2 | null
type SectionSaving = ArtifactType | null

interface MetaDraft {
  name: string
  description: string
  kind: SkillKind
  inputArity: InputArity
  allowedTools: string
  verifyChecks: VerifyCheckDraft[]
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
  onTryScript: () => Promise<ScriptTryResult>
}

const ARITY_OPTIONS: { value: InputArity; label: string }[] = [
  { value: 1, label: '1 документ' },
  { value: 2, label: '2 документа' },
  { value: null, label: 'Список' },
]

const KIND_OPTIONS: { value: SkillKind; label: string }[] = [
  { value: 'agent', label: 'agent' },
  { value: 'script', label: 'script' },
  { value: 'pipeline', label: 'pipeline' },
]

function emptyMeta(): MetaDraft {
  return {
    name: '',
    description: '',
    kind: 'agent',
    inputArity: 1,
    allowedTools: '',
    verifyChecks: [],
  }
}

const fieldCls = 'field'

function findArtifact(
  artifacts: SessionArtifact[],
  type: ArtifactType,
): SessionArtifact | undefined {
  return artifacts.find((a) => a.type === type)
}

function pipelinePromptHint(steps: PipelineStepDraft[]): string {
  const llmSteps = steps.filter((step) => step.type === 'llm')
  if (llmSteps.length === 0) return 'pipeline: llm-шагов нет — промпт не нужен'
  if (llmSteps.every((step) => step.system_prompt.trim())) {
    return 'pipeline: у всех llm-шагов свой промпт'
  }
  return 'pipeline: подставится в первый llm-шаг без своего промпта'
}

function pipelineScriptHint(steps: PipelineStepDraft[]): string {
  const scriptSteps = steps.filter((step) => step.type === 'script')
  if (scriptSteps.length === 0) return 'pipeline: script-шагов нет — код не нужен'
  if (scriptSteps.every((step) => step.code.trim())) {
    return 'pipeline: у всех script-шагов свой код'
  }
  return 'pipeline: подставится в первый script-шаг без своего кода'
}

function parseVerifyChecks(raw: unknown): VerifyCheckDraft[] {
  if (typeof raw === 'string') {
    return raw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
      .map((check) => ({ check }))
  }
  if (!Array.isArray(raw)) return []
  const out: VerifyCheckDraft[] = []
  for (const item of raw) {
    if (typeof item === 'string') {
      const check = item.trim()
      if (check) out.push({ check })
      continue
    }
    if (!item || typeof item !== 'object' || !('check' in item)) continue
    const obj = item as { check: unknown; params?: unknown }
    const check = String(obj.check).trim()
    if (!check) continue
    const params =
      obj.params && typeof obj.params === 'object' && !Array.isArray(obj.params)
        ? { ...(obj.params as Record<string, unknown>) }
        : undefined
    if (check === 'custom' && params && typeof params.id === 'string' && params.id.trim()) {
      out.push({ check: `custom:${params.id.trim()}` })
      continue
    }
    out.push(params ? { check, params } : { check })
  }
  return out
}

function parseMetaContent(content: string): MetaDraft {
  if (!content.trim()) return emptyMeta()
  try {
    const parsed = JSON.parse(content) as Record<string, unknown>
    const kind: SkillKind =
      parsed.kind === 'script' || parsed.kind === 'pipeline' ? parsed.kind : 'agent'
    const arityRaw = parsed.input_arity
    const inputArity: InputArity =
      arityRaw === 1 || arityRaw === 2 || arityRaw === null ? arityRaw : 1
    const tools = Array.isArray(parsed.allowed_tools)
      ? (parsed.allowed_tools as unknown[]).map(String).join(', ')
      : ''
    return {
      name: typeof parsed.name === 'string' ? parsed.name : '',
      description: typeof parsed.description === 'string' ? parsed.description : '',
      kind,
      inputArity,
      allowedTools: tools,
      verifyChecks: parseVerifyChecks(parsed.verify_checks),
    }
  } catch {
    return emptyMeta()
  }
}

function metaToPatch(draft: MetaDraft): SkillMetaPatch {
  const tools = draft.allowedTools
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
  const checks = draft.verifyChecks.map((item) =>
    item.params && Object.keys(item.params).length > 0
      ? { check: item.check, params: item.params }
      : { check: item.check },
  )
  return {
    name: draft.name.trim(),
    description: draft.description,
    kind: draft.kind,
    input_arity: draft.inputArity,
    allowed_tools: draft.kind === 'agent' ? tools : [],
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

function formatCount(n: number): string {
  return n.toLocaleString('ru-RU')
}

function previewTruncated(preview: string, len: number): boolean {
  return preview.endsWith('…[truncated]') || len > preview.length
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
  onTryScript,
}: ArtifactsPanelProps) {
  const [promptDraft, setPromptDraft] = useState('')
  const [scriptDraft, setScriptDraft] = useState('')
  const [metaDraft, setMetaDraft] = useState<MetaDraft>(emptyMeta)
  const [serverPrompt, setServerPrompt] = useState('')
  const [serverScript, setServerScript] = useState('')
  const [serverMetaSnap, setServerMetaSnap] = useState(() => metaSnapshot(emptyMeta()))
  const [saving, setSaving] = useState<SectionSaving>(null)
  const [saveErrors, setSaveErrors] = useState<Partial<Record<ArtifactType, string>>>({})
  const [savedFlash, setSavedFlash] = useState<Partial<Record<ArtifactType, boolean>>>({})
  const [nameClientError, setNameClientError] = useState(false)
  const [lastRun, setLastRun] = useState<ScriptTryResult | null>(null)
  const [tryError, setTryError] = useState<string | null>(null)
  const [inFlight, setInFlight] = useState(false)

  const metaRef = useRef<HTMLDivElement>(null)
  const stepsRef = useRef<HTMLDivElement>(null)
  const promptRef = useRef<HTMLTextAreaElement>(null)
  const scriptRef = useRef<HTMLTextAreaElement>(null)
  const nameRef = useRef<HTMLInputElement>(null)
  const stepsHeadingId = useId()
  const dirtyRef = useRef({ meta: false, prompt: false, script: false })
  const flashTimers = useRef<Partial<Record<ArtifactType, ReturnType<typeof setTimeout>>>>({})
  const inFlightRef = useRef(false)

  const promptArt = findArtifact(artifacts, 'prompt')
  const scriptArt = findArtifact(artifacts, 'script')
  const metaArt = findArtifact(artifacts, 'meta')
  const stepsArt = findArtifact(artifacts, 'steps')

  const dirtyMeta = metaSnapshot(metaDraft) !== serverMetaSnap
  const dirtyPrompt = promptDraft !== serverPrompt
  const dirtyScript = scriptDraft !== serverScript
  dirtyRef.current = { meta: dirtyMeta, prompt: dirtyPrompt, script: dirtyScript }

  useEffect(() => {
    setPromptDraft('')
    setScriptDraft('')
    setMetaDraft(emptyMeta())
    setServerPrompt('')
    setServerScript('')
    setServerMetaSnap(metaSnapshot(emptyMeta()))
    setSaving(null)
    setSaveErrors({})
    setSavedFlash({})
    setNameClientError(false)
    setLastRun(null)
    setTryError(null)
    setInFlight(false)
    inFlightRef.current = false
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
    if (highlightType === 'steps') {
      stepsRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
      stepsRef.current?.focus({ preventScroll: true })
      return
    }
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
    el?.focus({ preventScroll: true })
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
  const parsedSteps = parseStepsArtifact(stepsArt?.content ?? '')
  const showSteps = Boolean(stepsArt) || kind === 'pipeline'

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

  const goToScriptLine = (lineNo: number) => {
    const el = scriptRef.current
    if (!el) return
    const lines = scriptDraft.split('\n')
    if (lineNo < 1 || lineNo > lines.length) return
    let start = 0
    for (let i = 0; i < lineNo - 1; i++) start += lines[i].length + 1
    const end = start + lines[lineNo - 1].length
    el.focus()
    el.setSelectionRange(start, end)
    el.scrollIntoView({ block: 'nearest' })
  }

  const handleTryScript = async () => {
    if (inFlightRef.current) return
    if (!scriptDraft.trim() || streaming || saving === 'script') return
    inFlightRef.current = true
    setInFlight(true)
    setTryError(null)
    try {
      if (dirtyScript) {
        const art = await onSaveScript(scriptDraft)
        setScriptDraft(art.content)
        setServerScript(art.content)
        flashSaved('script')
        clearHighlightIf('script')
      }
      const result = await onTryScript()
      setLastRun(result)
    } catch (e) {
      setTryError(extractApiDetail(e))
    } finally {
      inFlightRef.current = false
      setInFlight(false)
    }
  }

  const dryStatus = scriptDryRun(artifacts)
  const runState = dryRunState({
    status: dryStatus,
    artifactUpdatedAt: scriptArt?.updated_at,
    dirty: dirtyScript,
  })
  const runMeta =
    runState === 'none'
      ? 'прогон нужен для сборки'
      : runState === 'ok' && dryStatus?.time
        ? formatUpdatedAt(dryStatus.time)
        : runState === 'stale'
          ? 'код менялся после прогона — прогоните снова'
          : null
  const tryDisabled =
    !scriptDraft.trim() || inFlight || inputsDisabled || saving === 'script'
  const tryTitle = !scriptDraft.trim()
    ? 'Добавьте код скрипта'
    : inputsDisabled
      ? 'Идёт генерация'
      : inFlight
        ? 'Прогоняю…'
        : undefined
  const failedRun = lastRun && !lastRun.ok ? lastRun : null
  const errorText =
    failedRun?.error ?? tryError ?? (runState === 'error' ? dryStatus?.error ?? null : null)
  const errorStage = stageLabel(
    failedRun ? failedRun.stage : runState === 'error' ? dryStatus?.stage : null,
  )
  const errorLine = errorLineNo(dryStatus, failedRun)
  const errorLineText = errorSourceLine(dryStatus, failedRun)
  const showDryRunError = Boolean(
    tryError || failedRun || (runState === 'error' && dryStatus?.error),
  )
  const showSuccessPreview = Boolean(
    lastRun?.ok &&
      (runState === 'ok' || runState === 'none' || dirtyScript),
  )

  const emptyArtifacts = artifacts.length === 0 && !loading

  const sectionShell = (
    type: ArtifactType,
    invalid: boolean,
    children: ReactNode,
  ) => {
    const highlighted = highlightType === type
    return (
      <div
        ref={
          type === 'meta' ? metaRef : type === 'steps' ? stepsRef : undefined
        }
        role={type === 'steps' ? 'group' : undefined}
        aria-labelledby={type === 'steps' ? stepsHeadingId : undefined}
        tabIndex={type === 'steps' ? -1 : undefined}
        aria-invalid={type === 'steps' && invalid ? true : undefined}
        aria-describedby={
          type === 'steps' && invalid ? 'steps-error' : undefined
        }
        className={
          'rounded-md border bg-surface p-3 ' +
          (invalid ? 'border-danger-line ' : 'border-line ') +
          (highlighted ? 'ring-2 ring-danger-line ' : '') +
          (type === 'prompt' && hasMeta && kind === 'script' ? 'opacity-70 ' : '') +
          (type === 'script' && hasMeta && kind === 'agent' ? 'opacity-70 ' : '')
        }
      >
        {children}
      </div>
    )
  }

  const statusRow = (art: SessionArtifact | undefined) => (
    <span className="text-[10px] text-ink-faint">
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
          <span className="text-[10px] text-success-ink">Сохранено</span>
        )}
        <button
          type="button"
          className="btn-primary"
          disabled={disabled || inputsDisabled || saving === type}
          onClick={() => void onClick()}
        >
          {saving === type ? 'Сохраняю…' : label}
        </button>
      </div>
      {saveErrors[type] && (
        <p id={`${type}-save-error`} className="mt-1 text-xs text-danger-ink">
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
        className="flex h-full flex-col border-l border-line bg-surface"
      >
        <div className="flex flex-1 items-center justify-center p-4 text-center text-sm text-ink-faint">
          Выберите сессию или начните новый чат — здесь появится черновик скилла.
        </div>
      </div>
    )
  }

  return (
    <div
      role="region"
      aria-label="Черновик скилла"
      className="flex h-full flex-col border-l border-line bg-surface"
    >
      <div className="flex h-full flex-col gap-3 overflow-y-auto p-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-ink">Черновик скилла</h2>
          {streaming && (
            <span className="text-[10px] text-warning-ink">планировщик пишет…</span>
          )}
        </div>

        {error && (
          <p className="text-xs text-danger-ink">{error}</p>
        )}

        {loading && (
          <p className="text-xs text-ink-faint">Загружаю артефакты…</p>
        )}

        {emptyArtifacts && !loading && (
          <p className="text-[11px] text-ink-faint">
            Планировщик сохранит черновик инструментами, или заполните вручную.
          </p>
        )}

        {sectionShell('meta', metaArt?.is_valid === false || nameClientError, (
          <>
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="text-[11px] uppercase tracking-wide text-ink-faint">Meta</h3>
              {statusRow(metaArt)}
            </div>
            <label className="mb-2 block text-[11px] text-ink-faint">
              Имя
              <input
                ref={nameRef}
                type="text"
                className={`mt-1 ${fieldCls}`}
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
            <label className="mb-2 block text-[11px] text-ink-faint">
              Описание
              <textarea
                className={`mt-1 min-h-[3.5rem] ${fieldCls}`}
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
              <div className="mb-1 text-[11px] text-ink-faint">Kind</div>
              <div
                role="radiogroup"
                aria-label="Kind"
                className={`flex flex-wrap gap-1 ${inputsDisabled ? 'pointer-events-none text-ink-faint' : ''}`}
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
                        'rounded px-2 py-1 text-[11px] disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-ink-faint ' +
                        (active
                          ? 'bg-brand text-white'
                          : 'bg-surface-muted text-ink-muted hover:bg-surface-hover')
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
              <div className="mb-1 text-[11px] text-ink-faint">Вход</div>
              <div
                role="radiogroup"
                aria-label="Вход"
                className={`flex flex-wrap gap-1 ${inputsDisabled ? 'pointer-events-none text-ink-faint' : ''}`}
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
                        'rounded px-2 py-1 text-[11px] disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-ink-faint ' +
                        (active
                          ? 'bg-brand text-white'
                          : 'bg-surface-muted text-ink-muted hover:bg-surface-hover')
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
            <label className="mb-2 block text-[11px] text-ink-faint">
              allowed_tools
              <input
                type="text"
                className={`mt-1 ${fieldCls}`}
                value={metaDraft.allowedTools}
                disabled={inputsDisabled || metaDraft.kind !== 'agent'}
                placeholder="tool1, tool2"
                onChange={(e) => {
                  setMetaDraft((d) => ({ ...d, allowedTools: e.target.value }))
                  clearHighlightIf('meta')
                }}
              />
              {metaDraft.kind === 'script' && (
                <span className="mt-1 block text-[10px] text-ink-faint">
                  не используется для script
                </span>
              )}
              {metaDraft.kind === 'pipeline' && (
                <span className="mt-1 block text-[10px] text-ink-faint">
                  задаётся на шагах
                </span>
              )}
            </label>
            <div className="mb-1">
              <VerifyChecksPicker
                value={metaDraft.verifyChecks}
                disabled={inputsDisabled}
                onChange={(next) => {
                  setMetaDraft((d) => ({ ...d, verifyChecks: next }))
                  clearHighlightIf('meta')
                }}
              />
            </div>
            {(nameClientError || metaArt?.error) && (
              <p id="meta-error" className="mt-1 text-[11px] text-danger-ink">
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

        {showSteps &&
          sectionShell('steps', stepsArt?.is_valid === false, (
            <>
              <div className="mb-2 flex items-center justify-between gap-2">
                <h3
                  id={stepsHeadingId}
                  className="text-[11px] uppercase tracking-wide text-ink-faint"
                >
                  Steps
                </h3>
                {statusRow(stepsArt)}
              </div>
              <p className="mb-1 text-[10px] text-ink-faint">
                Только просмотр — шаги меняются в чате
              </p>
              {parsedSteps.steps.length > 0 ? (
                <StepsList steps={parsedSteps.steps} />
              ) : !parsedSteps.parseError ? (
                <p className="text-[11px] text-ink-faint">
                  Шагов пока нет — планировщик добавит их инструментом `save_skill_steps`.
                </p>
              ) : null}
              {(stepsArt?.error || parsedSteps.parseError) && (
                <p id="steps-error" className="mt-1 text-[11px] text-danger-ink">
                  {stepsArt?.error || parsedSteps.parseError}
                </p>
              )}
              {parsedSteps.parseError && stepsArt && (
                <details className="mt-1">
                  <summary className="cursor-pointer text-[11px] text-ink-faint">
                    сырой JSON
                  </summary>
                  <pre className="mt-1 overflow-auto max-h-40 whitespace-pre-wrap break-words rounded bg-surface-muted p-1.5 font-mono text-[11px] text-ink-muted">
                    {stepsArt.content}
                  </pre>
                </details>
              )}
            </>
          ))}

        {sectionShell('prompt', promptArt?.is_valid === false, (
          <>
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="text-[11px] uppercase tracking-wide text-ink-faint">Prompt</h3>
              {statusRow(promptArt)}
            </div>
            {hasMeta && kind === 'script' && (
              <p className="mb-1 text-[10px] text-ink-faint">
                нужен только для kind=agent
              </p>
            )}
            {hasMeta && kind === 'pipeline' && (
              <p className="mb-1 text-[10px] text-ink-faint">
                {pipelinePromptHint(parsedSteps.steps)}
              </p>
            )}
            <textarea
              ref={promptRef}
              className={`min-h-[8rem] ${fieldCls}`}
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
              <p id="prompt-error" className="mt-1 text-[11px] text-danger-ink">
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
              <h3 className="text-[11px] uppercase tracking-wide text-ink-faint">Script</h3>
              {statusRow(scriptArt)}
            </div>
            {hasMeta && kind === 'agent' && (
              <p className="mb-1 text-[10px] text-ink-faint">
                нужен только для kind=script
              </p>
            )}
            {hasMeta && kind === 'pipeline' && (
              <p className="mb-1 text-[10px] text-ink-faint">
                {pipelineScriptHint(parsedSteps.steps)}
              </p>
            )}
            <textarea
              ref={scriptRef}
              className={`min-h-[10rem] font-mono text-xs leading-relaxed ${fieldCls}`}
              placeholder="Python-скрипт скилла…"
              value={scriptDraft}
              disabled={inputsDisabled}
              aria-invalid={scriptArt?.is_valid === false}
              aria-describedby={
                [
                  scriptArt?.error ? 'script-error' : null,
                  saveErrors.script ? 'script-save-error' : null,
                  showDryRunError ? 'script-dry-run-error' : null,
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
              <p id="script-error" className="mt-1 text-[11px] text-danger-ink">
                {scriptArt.error}
              </p>
            )}
            <div
              role="status"
              aria-live="polite"
              className="mt-2 flex items-center justify-between gap-2"
            >
              <div className="min-w-0">
                <span className={dryRunBadgeClass(runState)}>{dryRunLabel(runState)}</span>
                {runMeta && (
                  <span className="ml-2 text-[10px] text-ink-faint">{runMeta}</span>
                )}
              </div>
              <div className="flex shrink-0 flex-col items-end">
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={tryDisabled}
                  aria-busy={inFlight}
                  title={tryTitle}
                  aria-description={tryTitle}
                  onClick={() => void handleTryScript()}
                >
                  {inFlight ? 'Прогоняю…' : 'Прогнать'}
                </button>
                {dirtyScript && (
                  <span className="text-[10px] text-ink-faint">
                    код сохранится перед прогоном
                  </span>
                )}
              </div>
            </div>
            {dirtyScript && showSuccessPreview && (
              <p className="mt-2 text-[11px] text-warning-ink">
                Результат относится к предыдущей версии кода
              </p>
            )}
            {showSuccessPreview && lastRun && (
              <div className="mt-2 text-[11px] text-ink-muted">
                <p>
                  {formatCount(lastRun.duration_ms)} мс
                  {lastRun.output_kind ? ` · выход ${lastRun.output_kind}` : ''}
                  {` · ${formatCount(lastRun.output_len)} симв.`}
                  {` · вход ${formatCount(lastRun.input_len)} симв.`}
                </p>
                {lastRun.verify && (
                  <div className="mt-1">
                    <p>
                      Проверки: {lastRun.verify.checks.filter((c) => c.passed).length}/
                      {lastRun.verify.checks.length}
                    </p>
                    {lastRun.verify.checks
                      .filter((c) => !c.passed || c.skipped)
                      .map((c) => (
                        <p key={`${c.check}-${c.reason ?? ''}`}>
                          {c.skipped
                            ? `${c.check} — пропущена`
                            : `${c.check}${c.reason ? ` — ${c.reason}` : ''}`}
                        </p>
                      ))}
                  </div>
                )}
                <details className="mt-1">
                  <summary className="cursor-pointer text-[11px] text-ink-faint">
                    Вход (input_preview)
                    {previewTruncated(lastRun.input_preview, lastRun.input_len) && (
                      <span className="badge-warning ml-2">Усечено</span>
                    )}
                  </summary>
                  {previewTruncated(lastRun.input_preview, lastRun.input_len) && (
                    <p className="mt-1 text-[10px] text-ink-faint">
                      показаны первые 2000 симв. из {formatCount(lastRun.input_len)}
                    </p>
                  )}
                  <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-surface-muted p-1.5 font-mono text-[11px] text-ink-muted">
                    {lastRun.input_preview}
                  </pre>
                </details>
                <details className="mt-1">
                  <summary className="cursor-pointer text-[11px] text-ink-faint">
                    Выход (output_preview)
                    {previewTruncated(lastRun.output_preview, lastRun.output_len) && (
                      <span className="badge-warning ml-2">Усечено</span>
                    )}
                  </summary>
                  {previewTruncated(lastRun.output_preview, lastRun.output_len) && (
                    <p className="mt-1 text-[10px] text-ink-faint">
                      показаны первые 2000 симв. из {formatCount(lastRun.output_len)}
                    </p>
                  )}
                  <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-surface-muted p-1.5 font-mono text-[11px] text-ink-muted">
                    {lastRun.output_preview}
                  </pre>
                </details>
              </div>
            )}
            {showDryRunError && (
              <div
                id="script-dry-run-error"
                className="mt-2 rounded-md border border-danger-line bg-danger-soft px-2 py-1.5 text-[11px] text-danger-ink"
              >
                {errorStage && (
                  <p>Ошибка на стадии: {errorStage}</p>
                )}
                {errorText && (
                  <p className="whitespace-pre-wrap break-words">{errorText}</p>
                )}
                {errorLine != null && errorLineText != null && (
                  <p className="mt-1 bg-danger-soft font-mono text-danger-ink">
                    {errorLine} │ {errorLineText}
                  </p>
                )}
                {errorLine != null && errorLine <= scriptDraft.split('\n').length && (
                  <button
                    type="button"
                    className="btn-ghost mt-1"
                    onClick={() => goToScriptLine(errorLine)}
                  >
                    Перейти к строке {errorLine}
                  </button>
                )}
              </div>
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
