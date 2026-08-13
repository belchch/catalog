import { useState } from 'react'
import type { ScanReport } from '../api.ts'

const GROUPS: {
  key: keyof ScanReport
  label: string
  tone: string
}[] = [
  { key: 'added', label: 'Добавлено', tone: 'text-success-ink' },
  { key: 'updated', label: 'Обновлено', tone: 'text-info-ink' },
  { key: 'renamed', label: 'Переименовано', tone: 'text-accent-ink' },
  { key: 'removed', label: 'Удалено', tone: 'text-danger-ink' },
  { key: 'skipped', label: 'Пропущено', tone: 'text-ink-faint' },
]

interface ScanReportViewProps {
  report: ScanReport
  emptyLabel?: string
}

export function ScanReportView({
  report,
  emptyLabel = 'Изменений нет',
}: ScanReportViewProps) {
  const [open, setOpen] = useState<Partial<Record<keyof ScanReport, boolean>>>({})
  const total = GROUPS.reduce((sum, g) => sum + report[g.key].length, 0)

  if (total === 0) {
    return <p className="text-xs text-ink-faint">{emptyLabel}</p>
  }

  return (
    <div className="space-y-2">
      {GROUPS.map((g) => {
        const items = report[g.key]
        const expanded = open[g.key] ?? false
        return (
          <div key={g.key} className="rounded border border-line bg-surface-muted px-2 py-1.5">
            <button
              type="button"
              className="flex w-full items-center justify-between gap-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              onClick={() =>
                setOpen((prev) => ({ ...prev, [g.key]: !expanded }))
              }
              disabled={items.length === 0}
              aria-expanded={items.length > 0 ? expanded : undefined}
            >
              <span className="text-xs text-ink">
                <span className={g.tone} aria-hidden="true">
                  ●
                </span>{' '}
                {g.label}
              </span>
              <span className="badge-neutral">{items.length}</span>
            </button>
            {expanded && items.length > 0 ? (
              <ul className="mt-1 max-h-32 space-y-0.5 overflow-y-auto pl-3">
                {items.map((item) => (
                  <li
                    key={item}
                    className="truncate text-[11px] text-ink-faint"
                    title={item}
                  >
                    {item}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}
