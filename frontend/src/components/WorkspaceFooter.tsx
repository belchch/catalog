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
        className="flex min-w-0 flex-1 items-center gap-2.5 rounded-control px-[11px] py-2 text-left text-sm font-medium text-ink transition-colors hover:bg-[var(--sidebar-brand-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        onClick={onOpenPicker}
        title={path ?? undefined}
        aria-haspopup="dialog"
        aria-label={`Выбрать воркспейс: ${label}`}
      >
        <FolderIcon className="size-[18px] shrink-0 text-ink-faint" />
        <span
          className={
            hasWorkspace
              ? 'truncate font-medium text-ink'
              : 'truncate font-normal text-ink-faint'
          }
        >
          {label}
        </span>
      </button>
      {hasWorkspace ? (
        <button
          type="button"
          className="catalog-sidebar__icon-button size-8"
          onClick={onRescan}
          disabled={rescanning}
          aria-label="Пересканировать папку"
          title="Пересканировать папку"
          aria-busy={rescanning}
        >
          {rescanning ? (
            <SpinnerIcon className="size-[18px]" />
          ) : (
            <RefreshIcon className="size-[18px]" />
          )}
        </button>
      ) : (
        <span aria-hidden="true" className="size-8 shrink-0" />
      )}
    </div>
  )
}
