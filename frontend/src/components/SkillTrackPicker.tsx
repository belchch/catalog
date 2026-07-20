import { useEffect, useId, useRef, useState } from 'react'
import type { SkillTrack } from '../api.ts'

interface SkillTrackPickerProps {
  tracks: SkillTrack[]
  onSelect: (track: SkillTrack) => Promise<void>
  onCancel: () => void
}

function arityLabel(arity: number | null): string {
  if (arity === 1) return '1 документ'
  if (arity === 2) return '2 документа'
  return 'Список'
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-md rounded-lg border border-slate-700 bg-slate-900 p-4 shadow-xl"
      >
        <div className="mb-2 flex items-center justify-between">
          <h2 id={titleId} className="text-sm font-semibold text-slate-100">
            Выбор операции
          </h2>
          <button
            type="button"
            className="text-xs text-slate-400 hover:text-slate-200 disabled:opacity-50"
            onClick={onCancel}
            disabled={submitting}
            aria-label="Закрыть"
          >
            ✕
          </button>
        </div>
        <p className="mb-3 text-xs text-slate-400">
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
                  'flex w-full items-start gap-2 rounded border px-3 py-2 text-left disabled:opacity-50 ' +
                  (active
                    ? 'border-indigo-500 bg-indigo-600/15'
                    : 'border-slate-700 bg-slate-800/60 hover:border-indigo-500 hover:bg-slate-800')
                }
                onClick={() => setSelectedIndex(index)}
              >
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium text-slate-100">{track.name}</div>
                  <div className="mt-0.5 text-[11px] text-slate-300">{track.operation}</div>
                  <div className="mt-0.5 text-[11px] text-slate-400">{track.rationale}</div>
                </div>
                <span className="shrink-0 rounded bg-slate-700/60 px-1 text-[10px] uppercase text-slate-400">
                  {arityLabel(track.input_arity)}
                </span>
              </button>
            )
          })}
        </div>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="rounded bg-slate-700 px-3 py-1 text-xs text-slate-200 disabled:opacity-50"
            onClick={onCancel}
            disabled={submitting}
          >
            Отмена
          </button>
          <button
            type="button"
            className="rounded bg-indigo-600 px-3 py-1 text-xs text-white disabled:opacity-50"
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
