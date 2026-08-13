import { useEffect, useId, useRef, useState } from 'react'
import { extractApiDetail } from '../api.ts'

const MIN_TIMEOUT = 30
const MAX_TIMEOUT = 300
const DEFAULT_TIMEOUT = 60

interface SessionTimeoutModalProps {
  currentSeconds: number
  onSave: (seconds: number) => Promise<void>
  onClose: () => void
}

export function SessionTimeoutModal({
  currentSeconds,
  onSave,
  onClose,
}: SessionTimeoutModalProps) {
  const titleId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const [value, setValue] = useState(
    Number.isFinite(currentSeconds) ? currentSeconds : DEFAULT_TIMEOUT,
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    inputRef.current?.focus()
    inputRef.current?.select()
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !saving) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, saving])

  const outOfRange = !Number.isInteger(value) || value < MIN_TIMEOUT || value > MAX_TIMEOUT

  const handleSave = async () => {
    if (outOfRange) {
      setError(`Укажите целое число от ${MIN_TIMEOUT} до ${MAX_TIMEOUT}`)
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onSave(value)
      onClose()
    } catch (e) {
      setError(extractApiDetail(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="modal-card max-w-sm"
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 id={titleId} className="text-sm font-semibold text-ink">
            Таймаут LLM сессии
          </h2>
          <button
            type="button"
            className="btn-ghost px-1"
            onClick={onClose}
            disabled={saving}
            aria-label="Закрыть"
          >
            ✕
          </button>
        </div>
        <p className="mb-3 text-xs text-ink-faint">
          Лимит ожидания ответа модели для этой сессии чата (секунды).
        </p>
        <label className="mb-1 block text-[11px] text-ink-faint">
          Таймаут, секунды
          <input
            ref={inputRef}
            type="number"
            min={MIN_TIMEOUT}
            max={MAX_TIMEOUT}
            step={1}
            className="field mt-1"
            value={value}
            onChange={(e) => setValue(Number(e.target.value))}
            disabled={saving}
          />
        </label>
        <p className="mb-2 text-[10px] text-ink-faint">
          от {MIN_TIMEOUT} до {MAX_TIMEOUT}, по умолчанию {DEFAULT_TIMEOUT}
        </p>
        {(error || outOfRange) && (
          <p className="mb-2 text-xs text-danger-ink">
            {error ?? `Укажите целое число от ${MIN_TIMEOUT} до ${MAX_TIMEOUT}`}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="btn-secondary"
            onClick={onClose}
            disabled={saving}
          >
            Отмена
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={() => void handleSave()}
            disabled={saving || outOfRange}
          >
            {saving ? 'Сохранение…' : 'Сохранить'}
          </button>
        </div>
      </div>
    </div>
  )
}
