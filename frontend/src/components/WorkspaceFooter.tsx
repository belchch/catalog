import { FolderIcon, RefreshIcon, SpinnerIcon } from './icons.tsx'

interface WorkspaceFooterProps {
  path: string | null
  displayName: string | null
  rescanning: boolean
  onOpenPicker: () => void
  onRescan: () => void
}

export function folderLabel(path: string | null, displayName: string | null): string {
  if (!path) return 'Папка не открыта'
  if (displayName && displayName.trim()) return displayName
  const parts = path.replace(/\/+$/, '').split('/')
  return parts[parts.length - 1] || path
}

export function WorkspaceFooter({
  path,
  displayName,
  rescanning,
  onOpenPicker,
  onRescan,
}: WorkspaceFooterProps) {
  const label = folderLabel(path, displayName)
  const hasWorkspace = Boolean(path)

  return (
    <div className="catalog-sidebar__footer">
      <button
        type="button"
        className="group flex min-w-0 flex-1 items-center gap-2.5 rounded-none py-[11px] pl-5 pr-3 text-left text-sm font-semibold text-ink transition-colors hover:bg-[var(--sidebar-brand-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
        onClick={onOpenPicker}
        title={path ?? undefined}
        aria-haspopup="dialog"
        aria-label={label}
      >
        <FolderIcon className="size-[18px] shrink-0 text-ink-faint" />
        <span
          className={
            'truncate ' + (hasWorkspace ? '' : 'font-normal text-ink-faint')
          }
        >
          {label}
        </span>
        <span
          aria-hidden="true"
          className="ml-auto shrink-0 text-base text-ink-faint transition-colors group-hover:text-ink-muted"
        >
          ⌄
        </span>
      </button>
      {hasWorkspace ? (
        <button
          type="button"
          className="catalog-sidebar__icon-button size-8"
          onClick={onRescan}
          disabled={rescanning}
          aria-label="Пересканировать"
          title="Пересканировать"
          aria-busy={rescanning}
        >
          {rescanning ? (
            <SpinnerIcon className="size-[18px]" />
          ) : (
            <RefreshIcon className="size-[18px]" />
          )}
        </button>
      ) : null}
    </div>
  )
}
