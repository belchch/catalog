import { useEffect, useMemo, useRef, useState } from 'react'
import type { SkillOut } from '../api.ts'

interface ToolsPopoverProps {
  open: boolean
  onClose: () => void
  skills: SkillOut[]
  attachedIds: string[]
  onToggle: (skillId: string, enabled: boolean) => void
  onCreateSkill?: () => void
  loading?: boolean
  anchorRef?: React.RefObject<HTMLElement | null>
}

export function ToolsPopover({
  open,
  onClose,
  skills,
  attachedIds,
  onToggle,
  onCreateSkill,
  loading = false,
}: ToolsPopoverProps) {
  const [query, setQuery] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)
  const attached = useMemo(() => new Set(attachedIds), [attachedIds])

  useEffect(() => {
    if (!open) return
    const onPointer = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) onClose()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, onClose])

  useEffect(() => {
    if (!open) setQuery('')
  }, [open])

  if (!open) return null

  const q = query.trim().toLowerCase()
  const filtered = q
    ? skills.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          (s.description ?? '').toLowerCase().includes(q),
      )
    : skills

  const enabled = filtered.filter((s) => attached.has(s.id))
  const disabled = filtered.filter((s) => !attached.has(s.id))
  const ordered = [...enabled, ...disabled]

  const guarantee = (s: SkillOut): string => {
    if (s.kind === 'script') return 'script'
    if (s.kind === 'pipeline') return 'pipeline'
    return 'agent'
  }

  return (
    <div
      ref={rootRef}
      role="dialog"
      aria-label="Инструменты сессии"
      className="absolute bottom-full left-0 z-30 mb-2 w-80 overflow-hidden rounded-card border border-line bg-surface shadow-card"
    >
      <div className="border-b border-line px-3 py-2">
        <p className="text-xs font-medium text-ink">Инструменты</p>
        <p className="text-[11px] text-ink-faint">
          Модель может вызвать разрешённые скиллы
        </p>
        <input
          type="search"
          className="field mt-2 w-full text-xs"
          placeholder="Поиск…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
      </div>
      <ul className="max-h-72 overflow-y-auto py-1" role="list">
        {loading && (
          <li className="px-3 py-2 text-xs text-ink-faint">Загрузка…</li>
        )}
        {!loading && ordered.length === 0 && (
          <li className="px-3 py-2 text-xs text-ink-faint">Нет скиллов</li>
        )}
        {ordered.map((s) => {
          const on = attached.has(s.id)
          return (
            <li
              key={s.id}
              className="flex items-start gap-2 px-3 py-2 hover:bg-surface-hover"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1">
                  <span className="truncate text-sm text-ink">{s.name}</span>
                  {s.tags.includes('python') && (
                    <span className="badge-info">python</span>
                  )}
                  {s.tags.includes('ai') && (
                    <span className="badge-accent">ai</span>
                  )}
                </div>
                <p className="truncate text-[11px] text-ink-faint">
                  {(s.description || 'Без описания').trim()}
                </p>
                <p className="text-[11px] text-ink-faint">{guarantee(s)}</p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={on}
                aria-label={on ? `Отключить ${s.name}` : `Включить ${s.name}`}
                className={
                  'mt-0.5 h-5 w-9 shrink-0 rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand ' +
                  (on ? 'bg-brand' : 'bg-surface-muted')
                }
                onClick={() => onToggle(s.id, !on)}
              >
                <span
                  className={
                    'block h-4 w-4 translate-y-0.5 rounded-full bg-surface shadow transition-transform ' +
                    (on ? 'translate-x-4' : 'translate-x-0.5')
                  }
                />
              </button>
            </li>
          )
        })}
      </ul>
      {onCreateSkill && (
        <div className="border-t border-line px-3 py-2">
          <button
            type="button"
            className="btn-secondary w-full"
            onClick={() => {
              onClose()
              onCreateSkill()
            }}
          >
            Создать скилл
          </button>
        </div>
      )}
    </div>
  )
}
