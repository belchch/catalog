import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import {
  extractApiDetail,
  saveProviderKey,
  type ProviderSetupOut,
  type SetupKeysInput,
} from '../api.ts'

const KEY_FIELDS: Record<string, keyof SetupKeysInput> = {
  openrouter: 'openrouter_api_key',
  zai: 'zai_api_key',
}

interface SettingsPanelProps {
  providers: ProviderSetupOut[]
  onClose: () => void
  onRefresh: () => Promise<void>
}

export function SettingsPanel({ providers, onClose, onRefresh }: SettingsPanelProps) {
  const titleId = useId()
  const sectionTitleId = useId()
  const closeRef = useRef<HTMLButtonElement>(null)
  const replaceBtnRefs = useRef<Record<string, HTMLButtonElement | null>>({})
  const inputRefs = useRef<Record<string, HTMLInputElement | null>>({})
  const pendingFocusId = useRef<string | null>(null)

  const [replacingId, setReplacingId] = useState<string | null>(null)
  const [values, setValues] = useState<Record<string, string>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [savingId, setSavingId] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState(false)
  const [statusMessage, setStatusMessage] = useState('')

  const busy = savingId !== null || refreshing

  useEffect(() => {
    closeRef.current?.focus({ preventScroll: true })
  }, [])

  useEffect(() => {
    if (replacingId) {
      inputRefs.current[replacingId]?.focus({ preventScroll: true })
    }
  }, [replacingId])

  useEffect(() => {
    const id = pendingFocusId.current
    if (!id) return
    const btn = replaceBtnRefs.current[id]
    if (btn) {
      pendingFocusId.current = null
      btn.focus({ preventScroll: true })
    }
  }, [providers, replacingId, savingId, refreshing])

  const collapseReplace = (id: string) => {
    setReplacingId((current) => (current === id ? null : current))
    setValues((current) => ({ ...current, [id]: '' }))
    setErrors((current) => {
      const next = { ...current }
      delete next[id]
      return next
    })
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || busy) return
      if (replacingId) {
        e.preventDefault()
        const id = replacingId
        collapseReplace(id)
        pendingFocusId.current = id
        return
      }
      onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [busy, onClose, replacingId])

  const openReplace = (id: string) => {
    if (busy) return
    setReplacingId((current) => {
      if (current && current !== id) {
        setValues((vals) => ({ ...vals, [current]: '' }))
        setErrors((errs) => {
          const next = { ...errs }
          delete next[current]
          return next
        })
      }
      return id
    })
    setValues((current) => ({ ...current, [id]: '' }))
  }

  const handleRefresh = async () => {
    setRefreshing(true)
    setStatusMessage('Обновляю статусы…')
    try {
      await onRefresh()
      setRefreshError(false)
      setStatusMessage('Ключ сохранён')
    } catch {
      setRefreshError(true)
      setStatusMessage('')
    } finally {
      setRefreshing(false)
    }
  }

  const handleSave = async (provider: ProviderSetupOut) => {
    const field = KEY_FIELDS[provider.id]
    if (!field || busy) return
    const trimmed = (values[provider.id] ?? '').trim()
    if (!trimmed) return
    setSavingId(provider.id)
    setRefreshError(false)
    setErrors((current) => {
      const next = { ...current }
      delete next[provider.id]
      return next
    })
    try {
      await saveProviderKey({ [field]: trimmed })
      setValues((current) => ({ ...current, [provider.id]: '' }))
      setReplacingId(null)
      pendingFocusId.current = provider.id
      setRefreshing(true)
      setStatusMessage('Обновляю статусы…')
      try {
        await onRefresh()
        setRefreshError(false)
        setStatusMessage('Ключ сохранён')
      } catch {
        setRefreshError(true)
        setStatusMessage('')
      }
    } catch (e) {
      setErrors((current) => ({ ...current, [provider.id]: extractApiDetail(e) }))
    } finally {
      setSavingId(null)
      setRefreshing(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="modal-card flex max-h-[80vh] max-w-md flex-col space-y-4"
      >
        <div className="flex shrink-0 items-center justify-between">
          <h2 id={titleId} className="text-sm font-semibold text-ink">
            Настройки
          </h2>
          <button
            ref={closeRef}
            type="button"
            className="btn-ghost px-1"
            onClick={onClose}
            disabled={busy}
            aria-label="Закрыть"
          >
            ✕
          </button>
        </div>

        <section
          aria-labelledby={sectionTitleId}
          className="flex min-h-0 flex-1 flex-col space-y-2 overflow-hidden"
        >
          <h3 id={sectionTitleId} className="text-[11px] text-ink-faint">
            Провайдеры
          </h3>
          <p className="text-[11px] text-ink-faint">
            Ключи хранятся локально и не показываются обратно.
          </p>
          {providers.length === 0 ? (
            <p className="text-xs text-ink-faint">
              Список провайдеров недоступен — обновите бэкенд.
            </p>
          ) : (
            <ul className="min-h-0 flex-1 space-y-2 overflow-y-auto">
              {providers.map((provider) => (
                <ProviderRow
                  key={provider.id}
                  provider={provider}
                  value={values[provider.id] ?? ''}
                  error={errors[provider.id] ?? null}
                  replacing={replacingId === provider.id}
                  saving={savingId === provider.id}
                  busy={busy}
                  onValueChange={(next) =>
                    setValues((current) => ({ ...current, [provider.id]: next }))
                  }
                  onReplace={() => openReplace(provider.id)}
                  onCancel={() => {
                    collapseReplace(provider.id)
                    pendingFocusId.current = provider.id
                  }}
                  onSave={() => void handleSave(provider)}
                  replaceBtnRef={(el) => {
                    replaceBtnRefs.current[provider.id] = el
                  }}
                  inputRef={(el) => {
                    inputRefs.current[provider.id] = el
                  }}
                />
              ))}
            </ul>
          )}
          {refreshError ? (
            <div className="space-y-2">
              <p role="alert" className="text-xs text-danger-ink">
                Ключ сохранён, но статусы не обновились
              </p>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => void handleRefresh()}
                disabled={busy}
              >
                Обновить
              </button>
            </div>
          ) : null}
          <span className="sr-only" role="status" aria-live="polite">
            {statusMessage}
          </span>
        </section>
      </div>
    </div>
  )
}

interface ProviderRowProps {
  provider: ProviderSetupOut
  value: string
  error: string | null
  replacing: boolean
  saving: boolean
  busy: boolean
  onValueChange: (value: string) => void
  onReplace: () => void
  onCancel: () => void
  onSave: () => void
  replaceBtnRef: (el: HTMLButtonElement | null) => void
  inputRef: (el: HTMLInputElement | null) => void
}

function ProviderRow({
  provider,
  value,
  error,
  replacing,
  saving,
  busy,
  onValueChange,
  onReplace,
  onCancel,
  onSave,
  replaceBtnRef,
  inputRef,
}: ProviderRowProps) {
  const baseId = useId()
  const inputId = `${baseId}-key`
  const hintId = `${baseId}-hint`
  const errorId = `${baseId}-error`
  const known = provider.id in KEY_FIELDS
  const envManaged = provider.managed_by_env
  const connected = provider.configured && !envManaged
  const showReplace = connected && known && !replacing
  const showForm = envManaged || !provider.configured || replacing || !known
  const formLocked = envManaged || !known
  const trimmed = value.trim()
  const canSubmit = trimmed.length > 0 && !busy && !formLocked
  const hint = envManaged
    ? 'Ключ задан через переменную окружения. Запись через интерфейс не применится.'
    : !known
      ? 'Этот провайдер пока нельзя настроить через интерфейс.'
      : null
  const describedBy = [hint ? hintId : null, error ? errorId : null]
    .filter(Boolean)
    .join(' ') || undefined

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    onSave()
  }

  return (
    <li className="rounded border border-line bg-surface-muted px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="text-xs font-medium text-ink">{provider.name}</span>
          {provider.active ? <span className="badge-info">активный</span> : null}
          {envManaged ? (
            <span className="badge-warning">через окружение</span>
          ) : connected ? (
            <span className="badge-success">подключён</span>
          ) : (
            <span className="badge-neutral">нет ключа</span>
          )}
        </div>
        {showReplace ? (
          <button
            ref={replaceBtnRef}
            type="button"
            className="btn-secondary"
            onClick={onReplace}
            disabled={busy}
          >
            Заменить ключ
          </button>
        ) : null}
      </div>
      {showForm ? (
        <form className="mt-2" aria-busy={saving} onSubmit={handleSubmit}>
          <div className="flex items-center gap-2">
            <label htmlFor={inputId} className="sr-only">
              API-ключ {provider.name}
            </label>
            <input
              ref={inputRef}
              id={inputId}
              type="password"
              className="field min-w-0 flex-1 border border-line-strong bg-surface disabled:opacity-60"
              placeholder="Вставьте API-ключ"
              autoComplete="off"
              spellCheck={false}
              value={value}
              disabled={busy || formLocked}
              aria-describedby={describedBy}
              onChange={(e) => onValueChange(e.target.value)}
            />
            <button type="submit" className="btn-primary shrink-0" disabled={!canSubmit}>
              {saving ? 'Сохранение…' : 'Сохранить'}
            </button>
            {replacing ? (
              <button
                type="button"
                className="btn-secondary shrink-0"
                onClick={onCancel}
                disabled={busy}
              >
                Отмена
              </button>
            ) : null}
          </div>
          {hint ? (
            <p id={hintId} className="mt-1 text-[11px] text-ink-faint">
              {hint}
            </p>
          ) : null}
          {error ? (
            <p id={errorId} role="alert" className="mt-1 text-xs text-danger-ink">
              {error}
            </p>
          ) : null}
        </form>
      ) : null}
    </li>
  )
}
