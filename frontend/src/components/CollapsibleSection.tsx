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
      <div className="catalog-section-header">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          className="catalog-section-header__title focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          onClick={() => onToggle(!open)}
        >
          <span className="catalog-section-header__chevron" aria-hidden="true">
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
