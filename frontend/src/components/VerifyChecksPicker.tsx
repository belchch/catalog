import { useEffect, useState } from 'react'
import {
  createCustomCheck,
  listCustomChecks,
  listVerifyCheckCatalog,
  trialCustomCheck,
  type CustomCheckOut,
} from '../api.ts'

export type VerifyCheckDraft = { check: string; params?: Record<string, unknown> }

const PARAM_CHECKS = new Set([
  'min_length',
  'max_length',
  'regex_matches',
  'has_section',
  'has_field',
  'table_parses',
])

interface VerifyChecksPickerProps {
  value: VerifyCheckDraft[]
  onChange: (next: VerifyCheckDraft[]) => void
  disabled?: boolean
}

export function VerifyChecksPicker({
  value,
  onChange,
  disabled = false,
}: VerifyChecksPickerProps) {
  const [open, setOpen] = useState(false)
  const [labels, setLabels] = useState<Record<string, string>>({})
  const [builtin, setBuiltin] = useState<string[]>([])
  const [custom, setCustom] = useState<CustomCheckOut[]>([])
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newPrompt, setNewPrompt] = useState('')
  const [sample, setSample] = useState('')
  const [trialMsg, setTrialMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    void Promise.all([listVerifyCheckCatalog(), listCustomChecks()]).then(
      ([cat, mine]) => {
        setBuiltin(cat.builtin)
        setLabels(cat.labels)
        setCustom(mine)
      },
    )
  }, [open])

  const selectedIds = new Set(
    value.map((v) => (v.check.startsWith('custom:') ? v.check : v.check)),
  )

  const addBuiltin = (id: string) => {
    if (value.some((v) => v.check === id)) return
    const params: Record<string, unknown> = {}
    if (id === 'min_length') params.min = 1
    if (id === 'max_length') params.max = 10000
    if (id === 'has_section') params.heading = 'Раздел'
    if (id === 'has_field') params.key = 'Поле'
    if (id === 'regex_matches') params.pattern = '.'
    onChange([...value, { check: id, params: Object.keys(params).length ? params : undefined }])
  }

  const addCustom = (c: CustomCheckOut) => {
    const key = `custom:${c.id}`
    if (value.some((v) => v.check === key)) return
    onChange([...value, { check: key }])
  }

  const removeAt = (idx: number) => {
    onChange(value.filter((_, i) => i !== idx))
  }

  const updateParams = (idx: number, key: string, raw: string) => {
    const next = value.map((v, i) => {
      if (i !== idx) return v
      const params = { ...(v.params || {}) }
      if (key === 'min' || key === 'max' || key === 'min_rows' || key === 'min_cols' || key === 'level') {
        const n = Number(raw)
        params[key] = Number.isFinite(n) ? n : raw
      } else {
        params[key] = raw
      }
      return { ...v, params }
    })
    onChange(next)
  }

  const labelFor = (v: VerifyCheckDraft): string => {
    if (v.check.startsWith('custom:')) {
      const id = v.check.slice('custom:'.length)
      return custom.find((c) => c.id === id)?.name || `Моя проверка (${id.slice(0, 6)})`
    }
    return labels[v.check] || v.check
  }

  const saveNew = async () => {
    if (!newName.trim() || !newPrompt.trim()) return
    setBusy(true)
    setTrialMsg(null)
    try {
      const row = await createCustomCheck({
        name: newName.trim(),
        prompt: newPrompt.trim(),
      })
      setCustom((prev) => [row, ...prev])
      addCustom(row)
      setCreating(false)
      setNewName('')
      setNewPrompt('')
      setSample('')
    } catch (e) {
      setTrialMsg(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const runTrial = async () => {
    if (!newPrompt.trim()) return
    setBusy(true)
    setTrialMsg(null)
    try {
      const r = await trialCustomCheck({
        prompt: newPrompt.trim(),
        sample,
      })
      setTrialMsg(
        r.passed
          ? 'PASS — проверка прошла на примере'
          : `FAIL — ${(r.failures || []).join('; ') || 'не прошла'}`,
      )
    } catch (e) {
      setTrialMsg(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="relative">
      <div className="mb-1 flex flex-wrap gap-1.5">
        {value.length === 0 && (
          <span className="text-[11px] text-ink-faint">Проверки не выбраны</span>
        )}
        {value.map((v, idx) => (
          <span key={`${v.check}-${idx}`} className="chip max-w-full">
            <span className="truncate">{labelFor(v)}</span>
            <button
              type="button"
              className="ml-0.5 text-ink-faint hover:text-ink"
              disabled={disabled}
              aria-label={`Убрать ${labelFor(v)}`}
              onClick={() => removeAt(idx)}
            >
              ×
            </button>
          </span>
        ))}
      </div>
      {value.map((v, idx) =>
        PARAM_CHECKS.has(v.check) ? (
          <div key={`p-${v.check}-${idx}`} className="mb-1 grid grid-cols-2 gap-1">
            {v.check === 'min_length' && (
              <input
                className="field text-[11px]"
                disabled={disabled}
                placeholder="min"
                value={String(v.params?.min ?? '')}
                onChange={(e) => updateParams(idx, 'min', e.target.value)}
              />
            )}
            {v.check === 'max_length' && (
              <input
                className="field text-[11px]"
                disabled={disabled}
                placeholder="max"
                value={String(v.params?.max ?? '')}
                onChange={(e) => updateParams(idx, 'max', e.target.value)}
              />
            )}
            {v.check === 'has_section' && (
              <input
                className="field col-span-2 text-[11px]"
                disabled={disabled}
                placeholder="heading"
                value={String(v.params?.heading ?? '')}
                onChange={(e) => updateParams(idx, 'heading', e.target.value)}
              />
            )}
            {v.check === 'has_field' && (
              <input
                className="field col-span-2 text-[11px]"
                disabled={disabled}
                placeholder="key"
                value={String(v.params?.key ?? '')}
                onChange={(e) => updateParams(idx, 'key', e.target.value)}
              />
            )}
            {v.check === 'regex_matches' && (
              <input
                className="field col-span-2 text-[11px]"
                disabled={disabled}
                placeholder="pattern"
                value={String(v.params?.pattern ?? '')}
                onChange={(e) => updateParams(idx, 'pattern', e.target.value)}
              />
            )}
          </div>
        ) : null,
      )}
      <button
        type="button"
        className="btn-secondary"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
      >
        Добавить проверку
      </button>
      {open && (
        <div className="absolute left-0 z-20 mt-1 w-80 overflow-hidden rounded-card border border-line bg-surface shadow-card">
          {!creating ? (
            <>
              <div className="border-b border-line px-3 py-2">
                <p className="text-xs font-medium text-ink">Стандартные</p>
              </div>
              <ul className="max-h-40 overflow-y-auto py-1">
                {builtin.map((id) => (
                  <li key={id}>
                    <button
                      type="button"
                      className="flex w-full px-3 py-1.5 text-left text-xs hover:bg-surface-hover disabled:text-ink-faint"
                      disabled={selectedIds.has(id)}
                      onClick={() => addBuiltin(id)}
                    >
                      {labels[id] || id}
                    </button>
                  </li>
                ))}
              </ul>
              <div className="border-b border-t border-line px-3 py-2">
                <p className="text-xs font-medium text-ink">Мои проверки</p>
              </div>
              <ul className="max-h-32 overflow-y-auto py-1">
                {custom.length === 0 && (
                  <li className="px-3 py-1.5 text-[11px] text-ink-faint">Пока пусто</li>
                )}
                {custom.map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      className="flex w-full px-3 py-1.5 text-left text-xs hover:bg-surface-hover disabled:text-ink-faint"
                      disabled={selectedIds.has(`custom:${c.id}`)}
                      onClick={() => addCustom(c)}
                    >
                      <span className="truncate">{c.name}</span>
                      <span className="badge-accent ml-1 shrink-0">AI</span>
                    </button>
                  </li>
                ))}
              </ul>
              <div className="border-t border-line px-3 py-2">
                <button
                  type="button"
                  className="btn-secondary w-full"
                  onClick={() => setCreating(true)}
                >
                  Новая проверка
                </button>
              </div>
            </>
          ) : (
            <div className="space-y-2 p-3">
              <p className="text-xs font-medium text-ink">Новая проверка</p>
              <input
                className="field w-full text-xs"
                placeholder="Название"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
              />
              <textarea
                className="field w-full text-xs"
                rows={3}
                placeholder="Утверждение о результате, которое должно быть верно"
                value={newPrompt}
                onChange={(e) => setNewPrompt(e.target.value)}
              />
              <textarea
                className="field w-full text-xs"
                rows={2}
                placeholder="Пример текста для прогона"
                value={sample}
                onChange={(e) => setSample(e.target.value)}
              />
              {trialMsg && (
                <p className="text-[11px] text-ink-muted whitespace-pre-wrap">{trialMsg}</p>
              )}
              <div className="flex gap-2">
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={busy}
                  onClick={() => void runTrial()}
                >
                  Прогнать
                </button>
                <button
                  type="button"
                  className="btn-primary"
                  disabled={busy || !newName.trim() || !newPrompt.trim()}
                  onClick={() => void saveNew()}
                >
                  Сохранить
                </button>
                <button
                  type="button"
                  className="btn-ghost"
                  disabled={busy}
                  onClick={() => setCreating(false)}
                >
                  Назад
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
