import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import {
  parseStepsArtifact,
  type ArtifactType,
  type SessionArtifact,
  type SkillKind,
  type SkillMetaPatch,
} from '../api.ts'
import { StepsList } from './StepsList.tsx'

type InputArity = 1 | 2 | null
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
  { value: 'pipeline', label: 'pipeline' },
]

const EMPTY_META: MetaDraft = {
  name: '',
  description: '',
  kind: 'agent',
  inputArity: 1,
  allowedTools: '',
  verifyChecks: '',
}

const fieldCls = 'field'

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
    const kind: SkillKind =
      parsed.kind === 'script' || parsed.kind === 'pipeline' ? parsed.kind : 'agent'
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
  const stepsRef = useRef<HTMLDivElement>(null)
  const promptRef = useRef<HTMLTextAreaElement>(null)
  const scriptRef = useRef<HTMLTextAreaElement>(null)
  const nameRef = useRef<HTMLInputElement>(null)
  const stepsHeadingId = useId()
  const dirtyRef = useRef({ meta: false, prompt: false, script: false })
  const flashTimers = useRef<Partial<Record<ArtifactType, ReturnType<typeof setTimeout>>>>({})

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
            <label className="mb-1 block text-[11px] text-ink-faint">
              verify_checks
              <input
                type="text"
                className={`mt-1 ${fieldCls}`}
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
                pipeline: подставится в первый llm-шаг без своего промпта
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
                pipeline: подставится в первый script-шаг без своего кода
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
