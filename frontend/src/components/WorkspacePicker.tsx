import { useCallback, useEffect, useId, useRef, useState } from 'react'
import type {
  FsEntry,
  ScanReport,
  WorkspaceOpenResult,
  WorkspaceOut,
} from '../api.ts'
import { ApiError, extractApiDetail } from '../api.ts'
import { ScanReportView } from './ScanReportView.tsx'

interface WorkspacePickerProps {
  recents: WorkspaceOut[]
  browse: (path?: string) => Promise<FsEntry[]>
  open: (path: string, confirm?: boolean) => Promise<WorkspaceOpenResult>
  onOpened: () => void
  onClose: () => void
  onBusyConflict: (detail: string) => void
}

type PendingPanel =
  | { kind: 'needs_init'; path: string }
  | { kind: 'needs_confirm'; path: string; scan: ScanReport }
  | { kind: 'error'; detail: string }

function folderName(path: string, displayName: string | null): string {
  if (displayName && displayName.trim()) return displayName
  const parts = path.replace(/\/+$/, '').split('/')
  return parts[parts.length - 1] || path
}

function formatLastOpened(value: string | null): string | null {
  if (!value) return null
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString()
}

function parentDir(path: string): string {
  const trimmed = path.replace(/\/+$/, '')
  const idx = trimmed.lastIndexOf('/')
  if (idx <= 0) return trimmed.startsWith('/') ? '/' : trimmed
  return trimmed.slice(0, idx) || '/'
}

export function WorkspacePicker({
  recents,
  browse,
  open,
  onOpened,
  onClose,
  onBusyConflict,
}: WorkspacePickerProps) {
  const titleId = useId()
  const closeRef = useRef<HTMLButtonElement>(null)
  const [stack, setStack] = useState<string[]>([])
  const [entries, setEntries] = useState<FsEntry[]>([])
  const [rootPath, setRootPath] = useState('')
  const [browseLoading, setBrowseLoading] = useState(true)
  const [browseError, setBrowseError] = useState<string | null>(null)
  const [pending, setPending] = useState<PendingPanel | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const currentBrowsePath = stack[stack.length - 1] ?? ''
  const atRoot = stack.length === 0
  const openablePath = currentBrowsePath || rootPath || (atRoot ? '.' : '')

  const loadBrowse = useCallback(
    async (path?: string) => {
      setBrowseLoading(true)
      setBrowseError(null)
      try {
        const list = await browse(path && path !== '' ? path : undefined)
        setEntries(list)
        if (!path || path === '') {
          if (list.length > 0) {
            setRootPath(parentDir(list[0].path))
          }
        }
      } catch (e) {
        setEntries([])
        setBrowseError(extractApiDetail(e))
      } finally {
        setBrowseLoading(false)
      }
    },
    [browse],
  )

  useEffect(() => {
    closeRef.current?.focus()
  }, [])

  useEffect(() => {
    void loadBrowse(currentBrowsePath)
  }, [currentBrowsePath, loadBrowse])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !submitting) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, submitting])

  const tryOpen = async (path: string, confirm = false) => {
    if (submitting) return
    setSubmitting(true)
    if (!confirm) setPending(null)
    try {
      const result = await open(path, confirm)
      if (result.status === 'ok') {
        onOpened()
        return
      }
      if (result.status === 'needs_init') {
        setPending({ kind: 'needs_init', path })
        return
      }
      if (result.status === 'needs_confirm') {
        setPending({
          kind: 'needs_confirm',
          path,
          scan: result.scan ?? {
            added: [],
            updated: [],
            renamed: [],
            removed: [],
            skipped: [],
          },
        })
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        onBusyConflict(e.detail)
        setPending({ kind: 'error', detail: e.detail })
        return
      }
      setPending({ kind: 'error', detail: extractApiDetail(e) })
    } finally {
      setSubmitting(false)
    }
  }

  const goInto = (path: string) => {
    setPending(null)
    if (stack.length === 0) {
      setRootPath(parentDir(path))
    }
    setStack((prev) => [...prev, path])
  }

  const goUp = () => {
    if (stack.length === 0) return
    setPending(null)
    setStack((prev) => prev.slice(0, -1))
  }

  return (
    <div className="modal-overlay">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="modal-card max-h-[80vh] max-w-2xl overflow-y-auto"
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 id={titleId} className="text-sm font-semibold text-ink">
            Открыть воркспейс
          </h2>
          <button
            ref={closeRef}
            type="button"
            className="btn-ghost px-1"
            onClick={onClose}
            disabled={submitting}
            aria-label="Закрыть"
          >
            ✕
          </button>
        </div>

        {recents.length > 0 ? (
          <section className="mb-4">
            <p className="mb-1 text-[11px] text-ink-faint">Недавние</p>
            <ul className="space-y-1">
              {recents.map((ws) => {
                const last = formatLastOpened(ws.last_opened)
                return (
                  <li key={ws.path}>
                    <button
                      type="button"
                      className="flex w-full items-center gap-2 rounded border border-line bg-surface-muted px-3 py-2 text-left hover:border-line-brand hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
                      disabled={submitting}
                      onClick={() => void tryOpen(ws.path, false)}
                      title={ws.path}
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-xs text-ink">
                          {folderName(ws.path, ws.display_name)}
                        </span>
                        <span className="block truncate text-[11px] text-ink-faint">
                          {ws.path}
                        </span>
                      </span>
                      {last ? (
                        <span className="shrink-0 text-[11px] text-ink-faint">
                          {last}
                        </span>
                      ) : null}
                    </button>
                  </li>
                )
              })}
            </ul>
          </section>
        ) : null}

        <section className="mb-4">
          <p className="mb-1 text-[11px] text-ink-faint">Обзор папок</p>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span
              className="min-w-0 flex-1 truncate text-xs text-ink"
              title={currentBrowsePath || undefined}
            >
              {currentBrowsePath || 'Корень'}
            </span>
            <button
              type="button"
              className="btn-secondary"
              onClick={goUp}
              disabled={stack.length === 0 || submitting}
            >
              Вверх
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={submitting || !openablePath}
              onClick={() => void tryOpen(openablePath, false)}
            >
              Открыть эту папку
            </button>
          </div>

          {browseLoading ? (
            <p className="text-xs text-ink-faint">Загрузка…</p>
          ) : browseError ? (
            <p className="text-xs text-danger-ink">{browseError}</p>
          ) : entries.length === 0 ? (
            <p className="text-xs text-ink-faint">Нет вложенных папок</p>
          ) : (
            <ul className="space-y-1">
              {entries.map((entry) => (
                <li
                  key={entry.path}
                  className="flex items-center gap-1 rounded border border-line bg-surface-muted"
                >
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2 text-left hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed"
                    disabled={submitting}
                    onClick={() => goInto(entry.path)}
                    title={entry.path}
                  >
                    <span aria-hidden="true">▱</span>
                    <span className="truncate text-xs text-ink">{entry.name}</span>
                    {entry.has_catalog ? (
                      <span className="badge-success shrink-0">воркспейс</span>
                    ) : null}
                  </button>
                  <button
                    type="button"
                    className="btn-secondary mr-2 shrink-0"
                    disabled={submitting}
                    onClick={() => void tryOpen(entry.path, false)}
                  >
                    Открыть
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {pending ? (
          <section className="rounded border border-line bg-surface-muted p-3">
            {pending.kind === 'needs_init' ? (
              <>
                <p className="mb-3 text-xs text-ink">
                  Папка пустая. Создать здесь воркспейс?
                </p>
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={submitting}
                    onClick={() => void tryOpen(pending.path, true)}
                  >
                    {submitting ? '…' : 'Создать воркспейс'}
                  </button>
                </div>
              </>
            ) : null}
            {pending.kind === 'needs_confirm' ? (
              <>
                <p className="mb-2 text-xs text-ink">
                  Папка содержит файлы. Сделать воркспейсом и проиндексировать?
                </p>
                <ScanReportView report={pending.scan} />
                <div className="mt-3 flex justify-end gap-2">
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={submitting}
                    onClick={() => void tryOpen(pending.path, true)}
                  >
                    {submitting ? 'Индексирую…' : 'Сделать воркспейсом и проиндексировать'}
                  </button>
                </div>
              </>
            ) : null}
            {pending.kind === 'error' ? (
              <p className="text-xs text-danger-ink">{pending.detail}</p>
            ) : null}
          </section>
        ) : null}
      </div>
    </div>
  )
}
