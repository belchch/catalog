import { useId, type ReactNode } from 'react'

interface CollapsibleSectionProps {
  title: string
  open: boolean
  onToggle: (next: boolean) => void
  actions?: ReactNode
  children: ReactNode
}

export function CollapsibleSection({
  title,
  open,
  onToggle,
  actions,
  children,
}: CollapsibleSectionProps) {
  const panelId = useId()

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          className="flex flex-1 items-center gap-1.5 text-sm font-semibold text-slate-200 hover:text-white"
          onClick={() => onToggle(!open)}
        >
          <span className="text-xs text-slate-400" aria-hidden="true">
            {open ? '▾' : '▸'}
          </span>
          <span>{title}</span>
        </button>
        {actions && <div className="flex items-center gap-1">{actions}</div>}
      </div>
      {open && (
        <div
          id={panelId}
          role="region"
          aria-label={title}
          className="flex flex-col gap-2 pt-1"
        >
          {children}
        </div>
      )}
    </div>
  )
}
