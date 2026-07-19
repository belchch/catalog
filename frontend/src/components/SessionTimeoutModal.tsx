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

  const fieldCls = 'w-full rounded bg-slate-800 px-2 py-1 text-xs text-slate-100'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-sm rounded-lg border border-slate-700 bg-slate-900 p-4 shadow-xl"
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 id={titleId} className="text-sm font-semibold text-slate-100">
            Таймаут LLM сессии
          </h2>
          <button
            type="button"
            className="text-xs text-slate-400 hover:text-slate-200"
            onClick={onClose}
            disabled={saving}
            aria-label="Закрыть"
          >
            ✕
          </button>
        </div>
        <p className="mb-3 text-xs text-slate-400">
          Лимит ожидания ответа модели для этой сессии чата (секунды).
        </p>
        <label className="mb-1 block text-[11px] text-slate-400">
          Таймаут, секунды
          <input
            ref={inputRef}
            type="number"
            min={MIN_TIMEOUT}
            max={MAX_TIMEOUT}
            step={1}
            className={`mt-1 ${fieldCls}`}
            value={value}
            onChange={(e) => setValue(Number(e.target.value))}
            disabled={saving}
          />
        </label>
        <p className="mb-2 text-[10px] text-slate-500">
          от {MIN_TIMEOUT} до {MAX_TIMEOUT}, по умолчанию {DEFAULT_TIMEOUT}
        </p>
        {(error || outOfRange) && (
          <p className="mb-2 text-xs text-red-400">
            {error ?? `Укажите целое число от ${MIN_TIMEOUT} до ${MAX_TIMEOUT}`}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="rounded bg-slate-700 px-3 py-1 text-xs text-slate-200"
            onClick={onClose}
            disabled={saving}
          >
            Отмена
          </button>
          <button
            type="button"
            className="rounded bg-indigo-600 px-3 py-1 text-xs text-white disabled:opacity-50"
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
