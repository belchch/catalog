import { RefreshIcon, SpinnerIcon } from './icons.tsx'

interface WorkspaceBarProps {
  path: string | null
  displayName: string | null
  rescanning: boolean
  onOpenPicker: () => void
  onRescan: () => void
}

function folderLabel(path: string | null, displayName: string | null): string {
  if (!path) return 'Папка не открыта'
  if (displayName && displayName.trim()) return displayName
  const parts = path.replace(/\/+$/, '').split('/')
  return parts[parts.length - 1] || path
}

export function WorkspaceBar({
  path,
  displayName,
  rescanning,
  onOpenPicker,
  onRescan,
}: WorkspaceBarProps) {
  const label = folderLabel(path, displayName)
  const hasWorkspace = Boolean(path)

  return (
    <div className="mb-1">
      <div className="catalog-project-title !mb-0 flex items-center gap-1 !p-0">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-2 rounded px-2.5 py-1.5 text-left hover:bg-[var(--sidebar-brand-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          onClick={onOpenPicker}
          title={path ?? undefined}
          aria-label={label}
        >
          <span aria-hidden="true">▱</span>
          <span
            className={
              'truncate ' + (hasWorkspace ? '' : 'text-ink-faint font-normal')
            }
          >
            {label}
          </span>
        </button>
        {hasWorkspace ? (
          <button
            type="button"
            className="inline-flex size-8 shrink-0 items-center justify-center rounded hover:bg-[var(--sidebar-brand-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-50"
            onClick={onRescan}
            disabled={rescanning}
            aria-label="Пересканировать"
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
      {!hasWorkspace ? (
        <button
          type="button"
          className="btn-secondary mx-2 mt-1"
          onClick={onOpenPicker}
        >
          Открыть папку
        </button>
      ) : null}
    </div>
  )
}
