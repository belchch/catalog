import { useEffect, useId, useRef, useState, type ReactNode, type Ref } from 'react'
import {
  createCustomCheck,
  extractApiDetail,
  hideCustomCheck,
  listCustomChecks,
  listVerifyCheckCatalog,
  previewCustomCheck,
  type CustomCheckOut,
  type VerifyChecksCatalog,
} from '../api.ts'

export type VerifyCheckDraft = {
  check: string
  params?: Record<string, unknown>
}

interface VerifyChecksPickerProps {
  value: VerifyCheckDraft[]
  disabled?: boolean
  onChange: (next: VerifyCheckDraft[]) => void
}

type PickerView = 'list' | 'create'
type BusyKind = null | 'preview' | 'create' | 'hide'

const PARAM_SPEC: Record<string, { key: string; kind: 'number' | 'text' }> = {
  min_length: { key: 'min', kind: 'number' },
  max_length: { key: 'max', kind: 'number' },
  regex_matches: { key: 'pattern', kind: 'text' },
  has_section: { key: 'heading', kind: 'text' },
  has_field: { key: 'key', kind: 'text' },
}

function cloneDraft(items: VerifyCheckDraft[]): VerifyCheckDraft[] {
  return items.map((item) => ({
    check: item.check,
    params: item.params ? { ...item.params } : undefined,
  }))
}

function customRefId(check: string): string | null {
  if (!check.startsWith('custom:')) return null
  const id = check.slice('custom:'.length).trim()
  return id || null
}

function isParamMissing(item: VerifyCheckDraft): boolean {
  const spec = PARAM_SPEC[item.check]
  if (!spec) return false
  const raw = item.params?.[spec.key]
  if (spec.kind === 'number') {
    if (typeof raw === 'number') return !Number.isFinite(raw)
    if (typeof raw === 'string') {
      const trimmed = raw.trim()
      return trimmed === '' || !/^-?\d+$/.test(trimmed)
    }
    return true
  }
  return typeof raw !== 'string' || raw.trim() === ''
}

function normalizeDraft(items: VerifyCheckDraft[]): VerifyCheckDraft[] {
  return items.map((item) => {
    const spec = PARAM_SPEC[item.check]
    if (!spec || !item.params) {
      return item.params && Object.keys(item.params).length > 0 ? item : { check: item.check }
    }
    const next = { ...item.params }
    if (spec.kind === 'number') {
      const raw = next[spec.key]
      if (typeof raw === 'string' && /^-?\d+$/.test(raw.trim())) {
        next[spec.key] = Number(raw.trim())
      }
    }
    return { check: item.check, params: next }
  })
}

function paramDisplay(item: VerifyCheckDraft): string | null {
  const spec = PARAM_SPEC[item.check]
  if (!spec || !item.params) return null
  const raw = item.params[spec.key]
  if (raw == null || raw === '') return null
  return String(raw)
}

function emptyForm() {
  return { name: '', prompt: '', sample: '' }
}

export function VerifyChecksPicker({
  value,
  disabled = false,
  onChange,
}: VerifyChecksPickerProps) {
  const titleId = useId()
  const stdHeadingId = useId()
  const mineHeadingId = useId()
  const missingHeadingId = useId()
  const triggerRef = useRef<HTMLButtonElement>(null)
  const firstRowRef = useRef<HTMLButtonElement>(null)
  const fallbackFocusRef = useRef<HTMLButtonElement>(null)
  const nameInputRef = useRef<HTMLInputElement>(null)
  const focusListAfterLoad = useRef(false)

  const [open, setOpen] = useState(false)
  const [view, setView] = useState<PickerView>('list')
  const [draft, setDraft] = useState<VerifyCheckDraft[]>([])
  const [catalog, setCatalog] = useState<VerifyChecksCatalog | null>(null)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [customChecks, setCustomChecks] = useState<CustomCheckOut[]>([])
  const [customError, setCustomError] = useState<string | null>(null)
  const [customLoading, setCustomLoading] = useState(false)
  const [busy, setBusy] = useState<BusyKind>(null)
  const [hideConfirmId, setHideConfirmId] = useState<string | null>(null)
  const [form, setForm] = useState(emptyForm)
  const [preview, setPreview] = useState<{
    passed: boolean
    failures: string[]
  } | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [createError, setCreateError] = useState<string | null>(null)
  const [hideError, setHideError] = useState<string | null>(null)
  const [catalogFetched, setCatalogFetched] = useState(false)
  const [customFetched, setCustomFetched] = useState(false)

  const labels = catalog?.labels ?? {}
  const loading = catalogLoading || customLoading
  const bootLoading =
    loading && !catalog && customChecks.length === 0 && !catalogError && !customError
  const invalid = draft.some(isParamMissing)
  const customById = new Map(customChecks.map((item) => [item.id, item]))

  const loadCatalogs = async () => {
    setCatalogLoading(true)
    setCustomLoading(true)
    setCatalogError(null)
    setCustomError(null)
    const [catalogResult, customResult] = await Promise.allSettled([
      listVerifyCheckCatalog(),
      listCustomChecks(),
    ])
    if (catalogResult.status === 'fulfilled') {
      setCatalog(catalogResult.value)
    } else {
      setCatalogError(extractApiDetail(catalogResult.reason))
    }
    setCatalogFetched(true)
    if (customResult.status === 'fulfilled') {
      setCustomChecks(customResult.value)
    } else {
      setCustomError(extractApiDetail(customResult.reason))
    }
    setCustomFetched(true)
    setCatalogLoading(false)
    setCustomLoading(false)
  }

  useEffect(() => {
    void loadCatalogs()
  }, [])

  const closeWithoutApply = () => {
    if (busy) return
    setOpen(false)
    setView('list')
    setHideConfirmId(null)
    setForm(emptyForm())
    setPreview(null)
    setPreviewError(null)
    setCreateError(null)
    setHideError(null)
    queueMicrotask(() => triggerRef.current?.focus())
  }

  const openModal = () => {
    if (disabled) return
    setDraft(cloneDraft(value))
    setView('list')
    setHideConfirmId(null)
    setForm(emptyForm())
    setPreview(null)
    setPreviewError(null)
    setCreateError(null)
    setHideError(null)
    setOpen(true)
    focusListAfterLoad.current = true
    void loadCatalogs()
  }

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (busy) return
      if (hideConfirmId) {
        setHideConfirmId(null)
        return
      }
      setOpen(false)
      setView('list')
      setHideConfirmId(null)
      setForm(emptyForm())
      setPreview(null)
      setPreviewError(null)
      setCreateError(null)
      setHideError(null)
      queueMicrotask(() => triggerRef.current?.focus())
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, busy, hideConfirmId])

  useEffect(() => {
    if (!open) return
    if (view === 'create') {
      nameInputRef.current?.focus()
      return
    }
    if (bootLoading) {
      focusListAfterLoad.current = true
      return
    }
    if (focusListAfterLoad.current) {
      const target = firstRowRef.current ?? fallbackFocusRef.current
      target?.focus()
      focusListAfterLoad.current = false
    }
  }, [open, view, bootLoading])

  const toggleCheck = (id: string) => {
    setDraft((current) => {
      const idx = current.findIndex((item) => item.check === id)
      if (idx >= 0) return current.filter((_, i) => i !== idx)
      return [...current, { check: id }]
    })
  }

  const setParam = (check: string, key: string, next: unknown) => {
    setDraft((current) =>
      current.map((item) => {
        if (item.check !== check) return item
        return { ...item, params: { ...(item.params ?? {}), [key]: next } }
      }),
    )
  }

  const applyAndClose = () => {
    if (bootLoading || invalid || busy) return
    onChange(normalizeDraft(draft))
    setOpen(false)
    setView('list')
    setHideConfirmId(null)
    queueMicrotask(() => triggerRef.current?.focus())
  }

  const goCreate = () => {
    setView('create')
    setForm(emptyForm())
    setPreview(null)
    setPreviewError(null)
    setCreateError(null)
  }

  const goList = () => {
    setView('list')
    setForm(emptyForm())
    setPreview(null)
    setPreviewError(null)
    setCreateError(null)
    focusListAfterLoad.current = true
  }

  const runPreview = async () => {
    if (busy || !form.prompt.trim() || !form.sample.trim()) return
    setBusy('preview')
    setPreview(null)
    setPreviewError(null)
    try {
      const result = await previewCustomCheck({
        prompt: form.prompt,
        sample: form.sample,
      })
      setPreview(result)
    } catch (e) {
      setPreviewError(extractApiDetail(e))
    } finally {
      setBusy(null)
    }
  }

  const saveCheck = async () => {
    if (busy || !form.name.trim() || !form.prompt.trim()) return
    setBusy('create')
    setCreateError(null)
    try {
      const created = await createCustomCheck({
        name: form.name,
        prompt: form.prompt,
      })
      setCustomChecks((current) => [created, ...current])
      setDraft((current) => {
        const id = `custom:${created.id}`
        if (current.some((item) => item.check === id)) return current
        return [...current, { check: id }]
      })
      goList()
    } catch (e) {
      setCreateError(extractApiDetail(e))
    } finally {
      setBusy(null)
    }
  }

  const confirmHide = async (id: string) => {
    if (busy) return
    setBusy('hide')
    setHideError(null)
    try {
      await hideCustomCheck(id)
      setCustomChecks((current) => current.filter((item) => item.id !== id))
      setDraft((current) => current.filter((item) => item.check !== `custom:${id}`))
      setHideConfirmId(null)
    } catch (e) {
      setHideError(extractApiDetail(e))
      setHideConfirmId(null)
    } finally {
      setBusy(null)
    }
  }

  const selectedIds = new Set(draft.map((item) => item.check))
  const builtinIds = catalog?.builtin ?? []
  const missing = draft.filter((item) => {
    const cid = customRefId(item.check)
    if (cid) {
      if (customLoading || customError) return false
      return !customById.has(cid)
    }
    if (!catalog) return false
    return !builtinIds.includes(item.check)
  })

  const triggerCount = value.length
  const triggerText = triggerCount > 0 ? `Проверки: ${triggerCount}` : 'Выбрать проверки'

  return (
    <div>
      <p className="text-[11px] text-ink-faint">Проверки результата</p>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {value.length === 0 ? (
          <p className="text-[11px] text-ink-faint">Проверки не выбраны</p>
        ) : (
          value.map((item) => (
            <SelectedChip
              key={item.check}
              item={item}
              labels={labels}
              customById={customById}
              catalogLoaded={catalogFetched && catalog !== null}
              customLoaded={customFetched && customError === null}
            />
          ))
        )}
      </div>
      <button
        ref={triggerRef}
        type="button"
        className="btn-secondary mt-1.5"
        disabled={disabled}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={triggerText}
        onClick={openModal}
      >
        {triggerText}
      </button>
      {open && (
        <div className="modal-overlay">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className="modal-card max-w-lg"
          >
            <div className="mb-3 flex items-center justify-between">
              <h2 id={titleId} className="text-sm font-semibold text-ink">
                {view === 'create' ? 'Новая проверка' : 'Проверки результата'}
              </h2>
              <button
                type="button"
                className="btn-ghost px-1"
                onClick={closeWithoutApply}
                disabled={busy !== null}
                aria-label="Закрыть"
              >
                ✕
              </button>
            </div>
            {view === 'list' ? (
              <>
                <div className="max-h-[60vh] space-y-3 overflow-y-auto">
                  {bootLoading ? (
                    <p className="text-xs text-ink-muted">Загружаю проверки…</p>
                  ) : (
                    <>
                      {(catalogError || customError) && (
                        <div
                          role="alert"
                          className="rounded border border-danger-line bg-danger-soft p-2 text-xs text-danger-ink"
                        >
                          <p>{[catalogError, customError].filter(Boolean).join(' ')}</p>
                          <button
                            type="button"
                            className="btn-secondary mt-2"
                            onClick={() => void loadCatalogs()}
                          >
                            Повторить
                          </button>
                        </div>
                      )}
                      {hideError && (
                        <div
                          role="alert"
                          className="rounded border border-danger-line bg-danger-soft p-2 text-xs text-danger-ink"
                        >
                          {hideError}
                        </div>
                      )}
                      {catalog && (
                        <section role="group" aria-labelledby={stdHeadingId}>
                          <h3
                            id={stdHeadingId}
                            className="text-[11px] uppercase tracking-wide text-ink-faint"
                          >
                            Стандартные
                          </h3>
                          <div className="mt-1">
                            {builtinIds.map((id, index) => {
                              const item = draft.find((entry) => entry.check === id)
                              const selected = Boolean(item)
                              return (
                                <CheckRow
                                  key={id}
                                  rowRef={index === 0 ? firstRowRef : undefined}
                                  checkId={id}
                                  label={labels[id] ?? id}
                                  selected={selected}
                                  disabled={busy !== null}
                                  onToggle={() => toggleCheck(id)}
                                >
                                  {selected && PARAM_SPEC[id] && (
                                    <ParamField
                                      checkId={id}
                                      spec={PARAM_SPEC[id]}
                                      value={item?.params?.[PARAM_SPEC[id].key]}
                                      invalid={item ? isParamMissing(item) : false}
                                      disabled={busy !== null}
                                      onChange={(next) => setParam(id, PARAM_SPEC[id].key, next)}
                                    />
                                  )}
                                </CheckRow>
                              )
                            })}
                          </div>
                        </section>
                      )}
                      <section role="group" aria-labelledby={mineHeadingId}>
                        <h3
                          id={mineHeadingId}
                          className="text-[11px] uppercase tracking-wide text-ink-faint"
                        >
                          Мои проверки
                        </h3>
                        {customLoading && customChecks.length === 0 && !customError ? (
                          <p className="mt-1 text-xs text-ink-muted">Загружаю проверки…</p>
                        ) : customChecks.length === 0 && customError ? null : customChecks.length === 0 ? (
                          <p className="mt-1 text-[11px] text-ink-faint">
                            Пока пусто — создайте первую
                          </p>
                        ) : (
                          <div className="mt-1">
                            {customChecks.map((item, index) => {
                              const checkId = `custom:${item.id}`
                              const selected = selectedIds.has(checkId)
                              const confirm = hideConfirmId === item.id
                              return (
                                <div key={item.id}>
                                  {confirm ? (
                                    <div className="rounded px-2 py-1.5">
                                      <p className="text-[11px] text-ink">
                                        Скрыть из списка? Она перестанет предлагаться, а скиллы,
                                        которые уже на неё ссылаются, не пройдут проверку.
                                      </p>
                                      <div className="mt-1.5 flex gap-2">
                                        <button
                                          type="button"
                                          className="btn-danger"
                                          disabled={busy !== null}
                                          onClick={() => void confirmHide(item.id)}
                                        >
                                          Скрыть
                                        </button>
                                        <button
                                          type="button"
                                          className="btn-secondary"
                                          disabled={busy !== null}
                                          onClick={() => setHideConfirmId(null)}
                                        >
                                          Отмена
                                        </button>
                                      </div>
                                    </div>
                                  ) : (
                                    <CheckRow
                                      rowRef={
                                        !catalog && index === 0 ? firstRowRef : undefined
                                      }
                                      checkId={checkId}
                                      label={item.name}
                                      selected={selected}
                                      disabled={busy !== null}
                                      prompt={item.prompt}
                                      custom
                                      onToggle={() => toggleCheck(checkId)}
                                      trailing={
                                        <button
                                          type="button"
                                          className="btn-ghost text-[11px]"
                                          disabled={busy !== null}
                                          onClick={(e) => {
                                            e.stopPropagation()
                                            setHideConfirmId(item.id)
                                          }}
                                        >
                                          Скрыть
                                        </button>
                                      }
                                    />
                                  )}
                                </div>
                              )
                            })}
                          </div>
                        )}
                      </section>
                      {missing.length > 0 && (
                        <section role="group" aria-labelledby={missingHeadingId}>
                          <h3
                            id={missingHeadingId}
                            className="text-[11px] uppercase tracking-wide text-ink-faint"
                          >
                            Недоступные
                          </h3>
                          <div className="mt-1">
                            {missing.map((item) => (
                              <CheckRow
                                key={item.check}
                                checkId={item.check}
                                label={labels[item.check] ?? item.check}
                                selected
                                disabled={busy !== null}
                                missing
                                onToggle={() => toggleCheck(item.check)}
                              />
                            ))}
                          </div>
                        </section>
                      )}
                    </>
                  )}
                </div>
                <div className="mt-4 flex justify-end gap-2">
                  <button
                    ref={fallbackFocusRef}
                    type="button"
                    className="btn-secondary mr-auto"
                    disabled={busy !== null}
                    onClick={goCreate}
                  >
                    Новая проверка
                  </button>
                  <button
                    type="button"
                    className="btn-secondary"
                    disabled={busy !== null}
                    onClick={closeWithoutApply}
                  >
                    Отмена
                  </button>
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={busy !== null || bootLoading || invalid}
                    onClick={applyAndClose}
                  >
                    Готово
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="max-h-[60vh] space-y-3 overflow-y-auto">
                  {createError && (
                    <div
                      role="alert"
                      className="rounded border border-danger-line bg-danger-soft p-2 text-xs text-danger-ink"
                    >
                      {createError}
                    </div>
                  )}
                  <label className="block text-[11px] text-ink-faint">
                    Название
                    <input
                      ref={nameInputRef}
                      type="text"
                      className="field mt-1"
                      value={form.name}
                      disabled={busy !== null}
                      onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                    />
                  </label>
                  <label className="block text-[11px] text-ink-faint">
                    Утверждение
                    <textarea
                      className="field mt-1"
                      rows={3}
                      placeholder="Что должно быть верно про результат"
                      value={form.prompt}
                      disabled={busy !== null}
                      onChange={(e) => setForm((f) => ({ ...f, prompt: e.target.value }))}
                    />
                  </label>
                  <label className="block text-[11px] text-ink-faint">
                    Пример результата
                    <textarea
                      className="field mt-1"
                      rows={4}
                      value={form.sample}
                      disabled={busy !== null}
                      onChange={(e) => setForm((f) => ({ ...f, sample: e.target.value }))}
                    />
                  </label>
                  <button
                    type="button"
                    className="btn-secondary"
                    disabled={busy !== null || !form.prompt.trim() || !form.sample.trim()}
                    onClick={() => void runPreview()}
                  >
                    {busy === 'preview' ? 'Прогоняю…' : 'Прогнать на примере'}
                  </button>
                  {(preview || previewError) && (
                    <div
                      role={previewError ? 'alert' : 'status'}
                      className={
                        previewError || (preview && !preview.passed)
                          ? 'rounded bg-danger-soft p-2 text-xs text-danger-ink'
                          : 'rounded bg-success-soft p-2 text-xs text-success-ink'
                      }
                    >
                      {previewError
                        ? previewError
                        : preview?.passed
                          ? 'PASS — проверка прошла на примере'
                          : `FAIL — ${preview?.failures.join('; ') ?? ''}`}
                    </div>
                  )}
                </div>
                <div className="mt-4 flex justify-end gap-2">
                  <button
                    type="button"
                    className="btn-secondary"
                    disabled={busy !== null}
                    onClick={goList}
                  >
                    Назад
                  </button>
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={busy !== null || !form.name.trim() || !form.prompt.trim()}
                    onClick={() => void saveCheck()}
                  >
                    {busy === 'create' ? 'Сохраняю…' : 'Сохранить проверку'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function SelectedChip({
  item,
  labels,
  customById,
  catalogLoaded,
  customLoaded,
}: {
  item: VerifyCheckDraft
  labels: Record<string, string>
  customById: Map<string, CustomCheckOut>
  catalogLoaded: boolean
  customLoaded: boolean
}) {
  const cid = customRefId(item.check)
  if (cid) {
    const custom = customById.get(cid)
    const missing = customLoaded && !custom
    return (
      <span className="chip">
        {custom?.name ?? item.check}
        {missing ? (
          <span className="badge-danger">нет в списке</span>
        ) : (
          <span className="badge-accent">AI</span>
        )}
      </span>
    )
  }
  const known = Boolean(labels[item.check])
  const missing = catalogLoaded && !known
  const suffix = paramDisplay(item)
  const name = labels[item.check] ?? item.check
  return (
    <span className="chip">
      {suffix ? `${name} · ${suffix}` : name}
      {missing && <span className="badge-danger">нет в списке</span>}
    </span>
  )
}

function CheckRow({
  checkId,
  label,
  selected,
  disabled,
  onToggle,
  children,
  trailing,
  prompt,
  custom,
  missing,
  rowRef,
}: {
  checkId: string
  label: string
  selected: boolean
  disabled: boolean
  onToggle: () => void
  children?: ReactNode
  trailing?: ReactNode
  prompt?: string
  custom?: boolean
  missing?: boolean
  rowRef?: Ref<HTMLButtonElement>
}) {
  const rowCls = selected
    ? 'bg-brand-soft text-ink'
    : disabled
      ? 'bg-surface-muted text-ink-faint cursor-not-allowed'
      : 'hover:bg-surface-hover'
  return (
    <div className={`rounded ${rowCls}`}>
      <div className="flex items-start">
        <button
          ref={rowRef}
          type="button"
          role="checkbox"
          aria-checked={selected}
          aria-label={`${label} (${checkId})`}
          disabled={disabled || (missing && !selected)}
          onClick={onToggle}
          className="min-w-0 flex-1 rounded px-2 py-1.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed"
        >
          <span className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-ink">{label}</span>
            {custom && <span className="badge-accent">AI</span>}
            {missing && <span className="badge-danger">нет в списке</span>}
            {!custom && !missing && (
              <span className="text-[10px] text-ink-faint">{checkId}</span>
            )}
          </span>
          {custom && prompt !== undefined && (
            <span className="block truncate text-[11px] text-ink-faint" title={prompt}>
              {prompt}
            </span>
          )}
          {missing && (
            <span className="block text-[11px] text-ink-faint">
              проверка скрыта — verify упадёт, снимите её
            </span>
          )}
        </button>
        {trailing ? <div className="shrink-0 py-1.5 pr-2">{trailing}</div> : null}
      </div>
      {children}
    </div>
  )
}

function ParamField({
  checkId,
  spec,
  value,
  invalid,
  disabled,
  onChange,
}: {
  checkId: string
  spec: { key: string; kind: 'number' | 'text' }
  value: unknown
  invalid: boolean
  disabled: boolean
  onChange: (next: unknown) => void
}) {
  const errorId = `${checkId}-${spec.key}-error`
  const display = value == null ? '' : String(value)
  return (
    <div className="ml-6 mt-1">
      <input
        type="text"
        inputMode={spec.kind === 'number' ? 'numeric' : undefined}
        className={
          invalid
            ? 'field bg-danger-soft border border-danger-line'
            : 'field'
        }
        aria-label={spec.key}
        placeholder={spec.key}
        aria-invalid={invalid}
        aria-describedby={invalid ? errorId : undefined}
        disabled={disabled}
        value={display}
        onChange={(e) => {
          const next = e.target.value
          if (spec.kind === 'number') {
            if (next.trim() === '') {
              onChange('')
              return
            }
            if (/^-?\d+$/.test(next.trim())) {
              onChange(Number(next.trim()))
              return
            }
            onChange(next)
            return
          }
          onChange(next)
        }}
        onClick={(e) => e.stopPropagation()}
      />
      {invalid && (
        <p id={errorId} className="mt-0.5 text-[10px] text-danger-ink">
          Заполните параметр
        </p>
      )}
    </div>
  )
}
