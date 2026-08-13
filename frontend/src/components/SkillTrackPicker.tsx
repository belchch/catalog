import { useEffect, useId, useRef, useState } from 'react'
import type { SkillTrack } from '../api.ts'

interface SkillTrackPickerProps {
  tracks: SkillTrack[]
  onSelect: (track: SkillTrack) => Promise<void>
  onCancel: () => void
}

function arityLabel(arity: number | null): string {
  if (arity == null) return 'Список'
  if (arity === 1) return '1 документ'
  if (arity === 2) return '2 документа'
  const mod10 = arity % 10
  const mod100 = arity % 100
  if (mod10 === 1 && mod100 !== 11) return `${arity} документ`
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return `${arity} документа`
  }
  return `${arity} документов`
}

export function SkillTrackPicker({
  tracks,
  onSelect,
  onCancel,
}: SkillTrackPickerProps) {
  const titleId = useId()
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [submitting, setSubmitting] = useState(false)
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([])

  useEffect(() => {
    itemRefs.current[selectedIndex]?.focus()
  }, [selectedIndex])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !submitting) onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel, submitting])

  const confirm = async () => {
    const track = tracks[selectedIndex]
    if (!track || submitting) return
    setSubmitting(true)
    try {
      await onSelect(track)
    } catch {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="modal-card max-w-md"
      >
        <div className="mb-2 flex items-center justify-between">
          <h2 id={titleId} className="text-sm font-semibold text-ink">
            Выбор операции
          </h2>
          <button
            type="button"
            className="btn-ghost px-1"
            onClick={onCancel}
            disabled={submitting}
            aria-label="Закрыть"
          >
            ✕
          </button>
        </div>
        <p className="mb-3 text-xs text-ink-faint">
          Уточните, что делаем с документами — от этого зависит скилл.
        </p>
        <div
          role="radiogroup"
          aria-label="Варианты операции"
          className="mb-3 space-y-2"
          onKeyDown={(e) => {
            if (submitting) return
            if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
              e.preventDefault()
              setSelectedIndex((i) => (i + 1) % tracks.length)
            } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
              e.preventDefault()
              setSelectedIndex((i) => (i - 1 + tracks.length) % tracks.length)
            } else if (e.key === 'Enter') {
              e.preventDefault()
              void confirm()
            }
          }}
        >
          {tracks.map((track, index) => {
            const active = index === selectedIndex
            return (
              <button
                key={`${track.name}-${index}`}
                ref={(el) => {
                  itemRefs.current[index] = el
                }}
                type="button"
                role="radio"
                aria-checked={active}
                tabIndex={active ? 0 : -1}
                disabled={submitting}
                className={
                  'flex w-full items-start gap-2 rounded border px-3 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-ink-faint ' +
                  (active
                    ? 'border-line-brand bg-brand-soft'
                    : 'border-line bg-surface-muted hover:border-line-brand hover:bg-surface-hover')
                }
                onClick={() => setSelectedIndex(index)}
              >
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium text-ink">{track.name}</div>
                  <div className="mt-0.5 text-[11px] text-ink-muted">{track.operation}</div>
                  <div className="mt-0.5 text-[11px] text-ink-faint">{track.rationale}</div>
                </div>
                <span className="badge-neutral shrink-0">{arityLabel(track.input_arity)}</span>
              </button>
            )
          })}
        </div>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="btn-secondary"
            onClick={onCancel}
            disabled={submitting}
          >
            Отмена
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={() => void confirm()}
            disabled={submitting || tracks.length === 0}
          >
            {submitting ? 'Собираю скилл…' : 'Собрать скилл'}
          </button>
        </div>
      </div>
    </div>
  )
}
