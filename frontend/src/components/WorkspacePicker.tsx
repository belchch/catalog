import { useCallback, useEffect, useId, useRef, useState } from 'react'
import type {
  FsEntry,
  ScanReport,
  WorkspaceBusyReason,
  WorkspaceOpenResult,
  WorkspaceOut,
} from '../api.ts'
import { ApiError, extractApiDetail } from '../api.ts'
import { ScanReportView } from './ScanReportView.tsx'
import { FolderIcon, SpinnerIcon } from './icons.tsx'

interface WorkspacePickerProps {
  recents: WorkspaceOut[]
  browse: (path?: string) => Promise<FsEntry[]>
  open: (path: string, confirm?: boolean) => Promise<WorkspaceOpenResult>
  onOpened: () => void
  onClose: () => void
  onBusyConflict: (detail: string) => void
  blocked: boolean
  blockedReason: WorkspaceBusyReason | null
}

type PendingPanel =
  | { kind: 'needs_init'; path: string }
  | { kind: 'needs_confirm'; path: string; scan: ScanReport }
  | { kind: 'error'; detail: string; path?: string }

type BusyPhase = 'checking' | 'creating' | 'indexing'
type BusySource = 'recent' | 'browse-current' | 'browse-entry' | 'panel'
type BusyTarget = { path: string; phase: BusyPhase; source: BusySource }

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

function blockedBannerText(reason: WorkspaceBusyReason | null): {
  title: string
  hint: string
  short: string
} {
  const hint =
    'Смотреть папки можно; открыть другую папку получится после завершения.'
  if (reason === 'run') {
    return {
      title: 'Идёт выполнение скилла — переключение воркспейса недоступно',
      hint,
      short: 'Идёт выполнение скилла',
    }
  }
  if (reason === 'session') {
    return {
      title: 'Агент отвечает — переключение воркспейса недоступно',
      hint: 'Смотреть папки можно; открыть другую папку получится, когда агент закончит ответ. Чат закрывать не нужно.',
      short: 'Агент отвечает',
    }
  }
  return {
    title: 'Воркспейс занят — переключение недоступно',
    hint,
    short: 'Воркспейс занят',
  }
}

function parentDir(path: string): string {
  const trimmed = path.replace(/\/+$/, '')
  const idx = trimmed.lastIndexOf('/')
  if (idx <= 0) return trimmed.startsWith('/') ? '/' : trimmed
  return trimmed.slice(0, idx) || '/'
}

function phaseLabel(phase: BusyPhase): string {
  if (phase === 'checking') return 'Проверяю папку…'
  if (phase === 'creating') return 'Создаю воркспейс…'
  return 'Индексирую файлы…'
}

function resolvePhase(confirm: boolean, pending: PendingPanel | null): BusyPhase {
  if (!confirm) return 'checking'
  if (pending?.kind === 'needs_init') return 'creating'
  if (pending?.kind === 'needs_confirm') return 'indexing'
  return 'checking'
}

function isBusyAt(
  busy: BusyTarget | null,
  source: BusySource,
  path: string,
): boolean {
  return busy?.source === source && busy.path === path
}

function pendingIdentity(pending: PendingPanel | null): string | null {
  if (!pending) return null
  if (pending.kind === 'error') return `error:${pending.path ?? ''}`
  return `${pending.kind}:${pending.path}`
}

function BusyLabel({ phase }: { phase: BusyPhase }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <SpinnerIcon className="size-3.5 shrink-0" />
      {phaseLabel(phase)}
    </span>
  )
}

function FolderPathLine({
  path,
  className = 'mb-2 truncate text-[11px] text-ink-faint',
}: {
  path: string
  className?: string
}) {
  return (
    <p className={className} title={path}>
      Папка: {path}
    </p>
  )
}

const SLOW_INDEXING_MS = 5000
const SLOW_INDEXING_HINT =
  'На больших папках это может занять несколько минут.'

export function WorkspacePicker({
  recents,
  browse,
  open,
  onOpened,
  onClose,
  onBusyConflict,
  blocked,
  blockedReason,
}: WorkspacePickerProps) {
  const titleId = useId()
  const bannerId = useId()
  const filterId = useId()
  const closeRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const panelActionRef = useRef<HTMLButtonElement>(null)
  const [stack, setStack] = useState<string[]>([])
  const [entries, setEntries] = useState<FsEntry[]>([])
  const [rootPath, setRootPath] = useState('')
  const [browseLoading, setBrowseLoading] = useState(true)
  const [browseError, setBrowseError] = useState<string | null>(null)
  const [pending, setPending] = useState<PendingPanel | null>(null)
  const [busy, setBusy] = useState<BusyTarget | null>(null)
  const [slowIndexing, setSlowIndexing] = useState(false)
  const [filter, setFilter] = useState('')

  const submitting = busy !== null
  const currentBrowsePath = stack[stack.length - 1] ?? ''
  const atRoot = stack.length === 0
  const openablePath = currentBrowsePath || rootPath || (atRoot ? '.' : '')
  const openDisabled = submitting || blocked
  const banner = blocked ? blockedBannerText(blockedReason) : null
  const openDescribedBy = blocked ? bannerId : undefined
  const blockedTitle = banner?.short
  const focusKey = pendingIdentity(pending)
  const currentBusy = isBusyAt(busy, 'browse-current', openablePath)
  const panelPath = pending?.path
  const panelBusy = panelPath ? isBusyAt(busy, 'panel', panelPath) : false
  const query = filter.trim().toLowerCase()
  const visibleEntries = query
    ? entries.filter((e) => e.name.toLowerCase().includes(query))
    : entries
  const showFilter = !browseLoading && !browseError && entries.length > 0

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
    closeRef.current?.focus({ preventScroll: true })
  }, [])

  useEffect(() => {
    void loadBrowse(currentBrowsePath)
  }, [currentBrowsePath, loadBrowse])

  useEffect(() => {
    setFilter('')
  }, [currentBrowsePath])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !submitting) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, submitting])

  useEffect(() => {
    if (busy?.phase !== 'indexing') {
      setSlowIndexing(false)
      return
    }
    const timer = window.setTimeout(() => setSlowIndexing(true), SLOW_INDEXING_MS)
    return () => window.clearTimeout(timer)
  }, [busy])

  useEffect(() => {
    if (!pending) return
    if (pending.kind === 'error') {
      panelRef.current?.focus({ preventScroll: true })
      return
    }
    panelActionRef.current?.focus({ preventScroll: true })
  }, [focusKey, pending])

  const tryOpen = async (path: string, confirm: boolean, source: BusySource) => {
    if (submitting || blocked) return
    setBusy({ path, phase: resolvePhase(confirm, pending), source })
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
        setPending({ kind: 'error', detail: e.detail, path })
        return
      }
      setPending({ kind: 'error', detail: extractApiDetail(e), path })
    } finally {
      setBusy(null)
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
        className="modal-card flex max-h-[80vh] max-w-2xl flex-col overflow-hidden"
      >
        <div className="shrink-0">
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

          {banner ? (
            <div
              id={bannerId}
              role="status"
              aria-live="polite"
              className="mb-4 flex items-start gap-2 rounded border border-warning-line bg-warning-soft px-3 py-2 text-warning-ink"
            >
              <span aria-hidden="true" className="shrink-0">
                ⚠
              </span>
              <div className="min-w-0">
                <p className="text-xs font-medium">{banner.title}</p>
                <p className="text-[11px] opacity-80">{banner.hint}</p>
              </div>
            </div>
          ) : null}

          {busy ? (
            <span className="sr-only" role="status" aria-live="polite">
              {phaseLabel(busy.phase)}
              {slowIndexing && busy.phase === 'indexing'
                ? ` ${SLOW_INDEXING_HINT}`
                : ''}
            </span>
          ) : null}

          {pending ? (
            <div
              ref={panelRef}
              tabIndex={-1}
              aria-live="polite"
              aria-atomic="true"
              className={
                pending.kind === 'error'
                  ? 'mb-3 max-h-[60vh] rounded border border-danger-line bg-danger-soft p-3'
                  : 'mb-3 max-h-[60vh] rounded border border-line-brand bg-brand-soft p-3'
              }
            >
              {pending.kind === 'needs_init' ? (
                <>
                  <p className="mb-2 text-xs text-ink">
                    Папка пустая. Создать здесь воркспейс?
                  </p>
                  <FolderPathLine path={pending.path} />
                  <div className="flex justify-end">
                    <button
                      ref={panelActionRef}
                      type="button"
                      className={
                        panelBusy
                          ? 'btn-primary whitespace-nowrap disabled:cursor-progress disabled:bg-brand disabled:text-white'
                          : 'btn-primary whitespace-nowrap'
                      }
                      disabled={openDisabled}
                      onClick={() => void tryOpen(pending.path, true, 'panel')}
                      title={blockedTitle}
                      aria-describedby={openDescribedBy}
                      aria-busy={panelBusy || undefined}
                    >
                      {panelBusy && busy ? (
                        <BusyLabel phase={busy.phase} />
                      ) : (
                        'Создать воркспейс'
                      )}
                    </button>
                  </div>
                </>
              ) : null}
              {pending.kind === 'needs_confirm' ? (
                <>
                  <p className="mb-2 text-xs text-ink">
                    Папка содержит файлы. Сделать воркспейсом и проиндексировать?
                  </p>
                  <FolderPathLine path={pending.path} />
                  <div className="mb-2 max-h-40 overflow-y-auto rounded border border-line bg-surface p-2">
                    <ScanReportView report={pending.scan} />
                  </div>
                  <div className="flex justify-end">
                    <button
                      ref={panelActionRef}
                      type="button"
                      className={
                        panelBusy
                          ? 'btn-primary whitespace-nowrap disabled:cursor-progress disabled:bg-brand disabled:text-white'
                          : 'btn-primary whitespace-nowrap'
                      }
                      disabled={openDisabled}
                      onClick={() => void tryOpen(pending.path, true, 'panel')}
                      title={blockedTitle}
                      aria-describedby={openDescribedBy}
                      aria-busy={panelBusy || undefined}
                    >
                      {panelBusy && busy ? (
                        <BusyLabel phase={busy.phase} />
                      ) : (
                        'Сделать воркспейсом и проиндексировать'
                      )}
                    </button>
                  </div>
                  {slowIndexing && busy?.phase === 'indexing' ? (
                    <p className="mt-2 text-[11px] text-ink-faint">
                      {SLOW_INDEXING_HINT}
                    </p>
                  ) : null}
                </>
              ) : null}
              {pending.kind === 'error' ? (
                <>
                  <p
                    className={
                      pending.path
                        ? 'mb-2 text-xs text-danger-ink'
                        : 'text-xs text-danger-ink'
                    }
                  >
                    {pending.detail}
                  </p>
                  {pending.path ? (
                    <FolderPathLine
                      path={pending.path}
                      className="truncate text-[11px] text-ink-faint"
                    />
                  ) : null}
                </>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto pr-1">
          {recents.length > 0 ? (
            <section className="mb-4">
              <p className="mb-1 text-[11px] text-ink-faint">Недавние</p>
              <ul className="space-y-1">
                {recents.map((ws) => {
                  const last = formatLastOpened(ws.last_opened)
                  const thisBusy = isBusyAt(busy, 'recent', ws.path)
                  return (
                    <li key={ws.path}>
                      <button
                        type="button"
                        className={
                          thisBusy
                            ? 'flex w-full items-center gap-2 rounded border border-line bg-surface-muted px-3 py-2 text-left hover:border-line-brand hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-progress disabled:opacity-60'
                            : 'flex w-full items-center gap-2 rounded border border-line bg-surface-muted px-3 py-2 text-left hover:border-line-brand hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60'
                        }
                        disabled={openDisabled}
                        onClick={() => void tryOpen(ws.path, false, 'recent')}
                        title={blockedTitle ?? ws.path}
                        aria-describedby={openDescribedBy}
                        aria-busy={thisBusy || undefined}
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-xs text-ink">
                            {folderName(ws.path, ws.display_name)}
                          </span>
                          <span className="block truncate text-[11px] text-ink-faint">
                            {ws.path}
                          </span>
                        </span>
                        {thisBusy && busy ? (
                          <span className="shrink-0 text-[11px] text-ink-faint">
                            <BusyLabel phase={busy.phase} />
                          </span>
                        ) : last ? (
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

          <section>
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
                className={
                  currentBusy
                    ? 'btn-secondary whitespace-nowrap disabled:cursor-progress'
                    : 'btn-secondary whitespace-nowrap'
                }
                disabled={openDisabled || !openablePath}
                onClick={() => void tryOpen(openablePath, false, 'browse-current')}
                title={blockedTitle}
                aria-describedby={openDescribedBy}
                aria-busy={currentBusy || undefined}
              >
                {currentBusy && busy ? (
                  <BusyLabel phase={busy.phase} />
                ) : (
                  'Открыть эту папку'
                )}
              </button>
            </div>

            {showFilter ? (
              <div className="mb-2">
                <label htmlFor={filterId} className="sr-only">
                  Фильтр по имени папки
                </label>
                <input
                  id={filterId}
                  type="search"
                  className="field"
                  placeholder="Фильтр по имени"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                />
              </div>
            ) : null}

            {browseLoading ? (
              <p className="text-xs text-ink-faint">Загрузка…</p>
            ) : browseError ? (
              <p className="text-xs text-danger-ink">{browseError}</p>
            ) : entries.length === 0 ? (
              <p className="text-xs text-ink-faint">Нет вложенных папок</p>
            ) : visibleEntries.length === 0 ? (
              <p className="text-xs text-ink-faint" role="status">
                Ничего не найдено
              </p>
            ) : (
              <ul className="space-y-1">
                {visibleEntries.map((entry) => {
                  const entryBusy = isBusyAt(busy, 'browse-entry', entry.path)
                  return (
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
                        <FolderIcon className="size-4 shrink-0 text-ink-faint" />
                        <span className="min-w-0 truncate text-xs text-ink">
                          {entry.name}
                        </span>
                        {entry.has_catalog ? (
                          <span className="badge-success shrink-0">воркспейс</span>
                        ) : null}
                      </button>
                      <button
                        type="button"
                        className={
                          entryBusy
                            ? 'btn-secondary mr-2 shrink-0 whitespace-nowrap disabled:cursor-progress'
                            : 'btn-secondary mr-2 shrink-0 whitespace-nowrap'
                        }
                        disabled={openDisabled}
                        onClick={() => void tryOpen(entry.path, false, 'browse-entry')}
                        title={blockedTitle}
                        aria-describedby={openDescribedBy}
                        aria-busy={entryBusy || undefined}
                      >
                        {entryBusy && busy ? (
                          <BusyLabel phase={busy.phase} />
                        ) : (
                          'Открыть'
                        )}
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
