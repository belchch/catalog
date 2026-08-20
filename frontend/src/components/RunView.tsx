import { useEffect, useState, type KeyboardEvent } from 'react'
import type { DocumentOut, RunArtifact } from '../api.ts'
import type { UseRunStreamResult } from '../hooks/useRunStream.ts'
import { ExportDocxButton } from './ExportDocxButton.tsx'
import { MarkdownView } from './MarkdownView.tsx'
import { segmentTraceSteps } from '../lib/traceSegments.ts'
import { TraceSteps } from './TraceSteps.tsx'

interface RunViewProps {
  run: UseRunStreamResult
  runId: string | null
  documents: DocumentOut[]
  onClose: () => void
  onSaveResult: (runId: string) => void
  savingResult: boolean
  savedDocs?: DocumentOut[]
  savedDoc?: DocumentOut | null
  onOpenDoc?: (docId: string) => void
}

const RESULT_DOC_CHIPS_LIMIT = 6

function docsWord(n: number): string {
  const n10 = n % 10
  const n100 = n % 100
  if (n10 === 1 && n100 !== 11) return 'документ'
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return 'документа'
  return 'документов'
}

function formatCreatedCount(n: number): string {
  return `Создано ${n} ${docsWord(n)}`
}

function isCollectionArtifact(a: RunArtifact): a is RunArtifact & { text: string[] } {
  return Array.isArray(a.text)
}

function itemsOf(a: RunArtifact): string[] {
  return Array.isArray(a.text) ? a.text : [a.text]
}

const ITEM_TITLE_RE = /^\s{0,3}#{1,6}\s+(.+)$/m
const ITEM_TITLE_MAX_LEN = 80

function itemTitle(text: string, index: number): string {
  const match = text.match(ITEM_TITLE_RE)
  const raw = match ? match[1].trim() : ''
  if (!raw) return `Элемент ${index + 1}`
  return raw.length > ITEM_TITLE_MAX_LEN ? `${raw.slice(0, ITEM_TITLE_MAX_LEN)}…` : raw
}

function createdDocIds(
  run: UseRunStreamResult,
  savedDocs: DocumentOut[],
  savedDoc: DocumentOut | null,
): string[] {
  if (run.outputDocIds.length > 0) return run.outputDocIds
  if (savedDocs.length > 0) return savedDocs.map((doc) => doc.id)
  const single = run.outputDocId ?? savedDoc?.id ?? null
  return single ? [single] : []
}

function resolveDoc(
  id: string,
  documents: DocumentOut[],
  savedDocs: DocumentOut[],
  savedDoc: DocumentOut | null,
): DocumentOut | null {
  return (
    documents.find((doc) => doc.id === id) ??
    savedDocs.find((doc) => doc.id === id) ??
    (savedDoc?.id === id ? savedDoc : null)
  )
}

const CHIP_INTERACTIVE =
  'hover:border-accent-line hover:bg-accent-soft hover:text-accent-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent'

interface CollectionPanelProps {
  items: string[]
  artifactKey: string
}

function CollectionPanel({ items, artifactKey }: CollectionPanelProps) {
  const [openSet, setOpenSet] = useState<Set<number>>(() => new Set([0]))

  const toggle = (index: number) => {
    setOpenSet((prev) => {
      const next = new Set(prev)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }

  if (items.length === 0) {
    return <p className="text-xs text-ink-faint">Пустой результат.</p>
  }

  return (
    <div className="flex flex-col gap-1">
      {items.map((item, index) => {
        const open = openSet.has(index)
        const headerId = `run-item-${artifactKey}-${index}`
        const panelId = `run-item-panel-${artifactKey}-${index}`
        return (
          <div key={index} className="rounded border border-line bg-surface">
            <button
              type="button"
              id={headerId}
              aria-expanded={open}
              aria-controls={panelId}
              className="flex w-full items-center gap-1.5 rounded px-2 py-1 text-left text-xs text-ink hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              onClick={() => toggle(index)}
            >
              <span aria-hidden>{open ? '▾' : '▸'}</span>
              <span className="min-w-0 flex-1 truncate">
                {index + 1}. {itemTitle(item, index)}
              </span>
            </button>
            {open && (
              <div
                id={panelId}
                role="region"
                aria-labelledby={headerId}
                className="border-t border-line px-2 py-1.5"
              >
                {item ? (
                  <MarkdownView text={item} defaultMode="md" className="text-sm text-ink" />
                ) : (
                  <p className="text-xs text-ink-faint">Пустой элемент.</p>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

interface CreatedDocsChipsProps {
  docIds: string[]
  documents: DocumentOut[]
  savedDocs: DocumentOut[]
  savedDoc: DocumentOut | null
  onOpenDoc?: (docId: string) => void
}

function CreatedDocsChips({
  docIds,
  documents,
  savedDocs,
  savedDoc,
  onOpenDoc,
}: CreatedDocsChipsProps) {
  const [expanded, setExpanded] = useState(false)
  const collapsible = docIds.length > RESULT_DOC_CHIPS_LIMIT
  const countLabel = `${docIds.length} ${docsWord(docIds.length)}`

  const chips = (
    <div
      id={collapsible ? 'run-created-docs' : undefined}
      className={
        'mt-1 flex flex-wrap gap-1' + (collapsible ? ' max-h-40 overflow-y-auto' : '')
      }
    >
      {docIds.map((id, index) => {
        const doc = resolveDoc(id, documents, savedDocs, savedDoc)
        const label = doc?.title || id.slice(0, 8)
        const full = doc?.title || id
        const title = index === 0 ? `${full} · основной` : full
        const cls = (index === 0 ? 'chip-brand ' : 'chip ') + (onOpenDoc ? CHIP_INTERACTIVE : '')
        if (onOpenDoc) {
          return (
            <button
              key={id}
              type="button"
              className={cls}
              title={title}
              aria-label={title}
              onClick={() => onOpenDoc(id)}
            >
              {label}
            </button>
          )
        }
        return (
          <span key={id} className={cls} title={title} aria-label={title}>
            {label}
          </span>
        )
      })}
    </div>
  )

  if (!collapsible) return chips

  if (!expanded) {
    return (
      <button
        type="button"
        className="btn-secondary mt-1"
        aria-expanded={false}
        aria-controls="run-created-docs"
        onClick={() => setExpanded(true)}
      >
        {`Показать ${countLabel}`}
      </button>
    )
  }

  return (
    <>
      {chips}
      <button
        type="button"
        className="btn-secondary mt-1"
        aria-expanded={true}
        aria-controls="run-created-docs"
        onClick={() => setExpanded(false)}
      >
        Скрыть список
      </button>
    </>
  )
}

export function RunView({
  run,
  runId,
  documents,
  onClose,
  onSaveResult,
  savingResult,
  savedDocs = [],
  savedDoc = null,
  onOpenDoc,
}: RunViewProps) {
  const statusOk = run.status === 'ok'
  const artifacts = run.artifacts
  const hasCollection = artifacts.some(isCollectionArtifact)
  const showTablist = artifacts.length > 1
  const plannedDocs =
    artifacts.length === 0 ? 1 : artifacts.reduce((sum, item) => sum + itemsOf(item).length, 0)
  const docIds = createdDocIds(run, savedDocs, savedDoc)
  const outputDocId = docIds[0] ?? null
  const outputDoc = outputDocId ? resolveDoc(outputDocId, documents, savedDocs, savedDoc) : null
  const canSaveResult = run.finished && statusOk && docIds.length === 0 && !!run.resultText
  const exportDocIds = docIds.length > 0 ? docIds : (run.meta?.inputDocs ?? [])
  const groupCount = segmentTraceSteps(run.steps).filter((seg) => seg.kind === 'group').length
  const artifactKeys = artifacts.map((item) => item.key).join('\0')
  const [activeKey, setActiveKey] = useState<string | null>(null)

  useEffect(() => {
    setActiveKey(artifactKeys ? artifactKeys.split('\0')[0] : null)
  }, [runId, artifactKeys])

  const active = artifacts.find((item) => item.key === activeKey) ?? artifacts[0] ?? null
  const activeIndex = active ? artifacts.indexOf(active) : 0
  const showDetail = active != null && (showTablist || isCollectionArtifact(active))

  const onTabKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (artifacts.length < 2) return
    const last = artifacts.length - 1
    let next = activeIndex
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault()
      const dir = e.key === 'ArrowRight' ? 1 : -1
      next = (activeIndex + dir + artifacts.length) % artifacts.length
    } else if (e.key === 'Home') {
      e.preventDefault()
      next = 0
    } else if (e.key === 'End') {
      e.preventDefault()
      next = last
    } else {
      return
    }
    const nextKey = artifacts[next]?.key
    if (!nextKey) return
    setActiveKey(nextKey)
    document.getElementById(`run-tab-${nextKey}`)?.focus()
  }

  const saveLabel = hasCollection
    ? `Сохранить как ${plannedDocs} ${docsWord(plannedDocs)}`
    : showTablist
      ? 'Сохранить как новые документы'
      : 'Сохранить как новый документ'
  const saveTitle = hasCollection
    ? `Будет создано ${plannedDocs} ${docsWord(plannedDocs)} в рабочей папке`
    : undefined

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-line px-4 py-2">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-ink">
            Прогон{runId ? ` ${runId.slice(0, 8)}` : ''}
          </h2>
          {run.status && (
            <span className={statusOk ? 'badge-success' : 'badge-danger'}>
              {run.status}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            ← К чату
          </button>
          {!run.finished && (
            <button
              type="button"
              className="btn-danger"
              onClick={run.cancel}
              disabled={run.cancelling}
            >
              {run.cancelling ? 'Останавливаю…' : 'Стоп'}
            </button>
          )}
        </div>
      </div>
      <div className="grid flex-1 grid-cols-1 gap-3 overflow-hidden p-3 md:grid-cols-2">
        <div className="overflow-y-auto rounded-md border border-line bg-surface-muted p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="text-xs font-semibold uppercase text-ink-faint">Лента шагов</h3>
            {groupCount >= 1 && (
              <span className="text-[10px] text-ink-faint">шагов: {groupCount}</span>
            )}
          </div>
          {run.meta && (
            <div className="mb-2 rounded border border-line bg-surface-muted p-2 font-mono text-[10px] text-ink-faint">
              <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                <span>
                  <span className="text-ink-faint">model:</span> {run.meta.model}
                </span>
                {run.meta.provider && (
                  <span>
                    <span className="text-ink-faint">provider:</span> {run.meta.provider}
                  </span>
                )}
                <span>
                  <span className="text-ink-faint">kind:</span> {run.meta.skillKind}
                </span>
                {run.meta.inputDocs.length > 0 && (
                  <span>
                    <span className="text-ink-faint">docs:</span> {run.meta.inputDocs.length}
                  </span>
                )}
              </div>
              {run.meta.systemPrompt && (
                <details className="mt-1">
                  <summary className="cursor-pointer text-ink-faint">системный промпт</summary>
                  <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words text-ink-faint">
                    {run.meta.systemPrompt}
                  </pre>
                </details>
              )}
            </div>
          )}
          <TraceSteps steps={run.steps} running={!run.finished} />
          {run.error && <p className="mt-2 text-xs text-danger-ink">Ошибка: {run.error}</p>}
          {run.closed && !run.finished && (
            <p className="mt-2 text-xs text-warning-ink">Соединение закрыто</p>
          )}
        </div>
        <div className="overflow-y-auto rounded-md border border-line bg-surface-muted p-3">
          <h3 className="mb-2 text-xs font-semibold uppercase text-ink-faint">Результат</h3>
          {docIds.length > 1 ? (
            <div className="mb-2 rounded border border-success-line bg-success-soft px-2 py-1 text-xs text-success-ink">
              <div role="status" aria-live="polite">
                <p>{formatCreatedCount(docIds.length)}</p>
                <p className="mt-1 text-[11px] text-success-ink">
                  {onOpenDoc ? 'Документы прогона — откройте нужный' : 'Документы прогона'}
                </p>
              </div>
              <CreatedDocsChips
                key={runId ?? ''}
                docIds={docIds}
                documents={documents}
                savedDocs={savedDocs}
                savedDoc={savedDoc}
                onOpenDoc={onOpenDoc}
              />
            </div>
          ) : outputDocId ? (
            <p className="mb-2 rounded border border-success-line bg-success-soft px-2 py-1 text-xs text-success-ink">
              Документ создан{outputDoc ? `: «${outputDoc.title}»` : ` (id ${outputDocId.slice(0, 8)})`}
            </p>
          ) : null}
          {canSaveResult && (
            <button
              type="button"
              className="btn-primary mb-2"
              disabled={savingResult}
              title={saveTitle}
              onClick={() => runId && onSaveResult(runId)}
            >
              {savingResult ? 'Сохраняю…' : saveLabel}
            </button>
          )}
          <div className="mb-2">
            <ExportDocxButton
              docIds={exportDocIds}
              title={outputDoc?.title}
              disabled={!run.finished || exportDocIds.length === 0}
              disabledHint={
                !run.finished
                  ? 'Дождитесь завершения прогона'
                  : 'Нет документов для выгрузки'
              }
            />
          </div>
          {showDetail && active ? (
            <>
              {showTablist && (
                <div
                  role="tablist"
                  aria-label="Результаты прогона"
                  className="mb-2 flex flex-wrap gap-1"
                  onKeyDown={onTabKeyDown}
                >
                  {artifacts.map((item, index) => {
                    const selected = item.key === active.key
                    const collection = isCollectionArtifact(item)
                    const n = itemsOf(item).length
                    const baseLabel = item.description?.trim() || item.key
                    const tabLabel = collection ? `${baseLabel} · ${n}` : baseLabel
                    const tabTitle = collection
                      ? item.description?.trim()
                        ? `${item.key} — ${item.description} · элементов: ${n}`
                        : `${item.key} · элементов: ${n}`
                      : item.description?.trim()
                        ? `${item.key} — ${item.description}`
                        : item.key
                    return (
                      <button
                        key={`${index}-${item.key}`}
                        type="button"
                        role="tab"
                        id={`run-tab-${item.key}`}
                        aria-selected={selected}
                        aria-controls={`run-panel-${item.key}`}
                        tabIndex={selected ? 0 : -1}
                        title={tabTitle}
                        className={
                          'max-w-[12rem] truncate rounded px-2 py-1 text-[11px] focus-visible:ring-2 focus-visible:ring-brand ' +
                          (selected
                            ? 'bg-brand text-white'
                            : 'bg-surface-muted text-ink-muted hover:bg-surface-hover')
                        }
                        onClick={() => setActiveKey(item.key)}
                      >
                        {tabLabel}
                      </button>
                    )
                  })}
                </div>
              )}
              <div className="mb-2 flex items-center gap-2 text-[11px] text-ink-faint">
                <span className="font-mono text-ink">{active.key}</span>
                {activeIndex === 0 && <span className="badge-neutral">основной</span>}
                {isCollectionArtifact(active) && (
                  <span className="text-ink-faint">элементов: {itemsOf(active).length}</span>
                )}
              </div>
              <div
                role={showTablist ? 'tabpanel' : undefined}
                id={showTablist ? `run-panel-${active.key}` : undefined}
                aria-labelledby={showTablist ? `run-tab-${active.key}` : undefined}
                tabIndex={showTablist ? 0 : undefined}
              >
                {Array.isArray(active.text) ? (
                  <CollectionPanel
                    key={`${runId ?? ''} ${active.key} ${artifactKeys}`}
                    items={active.text}
                    artifactKey={active.key}
                  />
                ) : active.text ? (
                  <MarkdownView
                    text={active.text}
                    defaultMode="md"
                    className="text-sm text-ink"
                  />
                ) : (
                  <p className="text-xs text-ink-faint">Пустой результат.</p>
                )}
              </div>
            </>
          ) : run.resultText ? (
            <MarkdownView
              text={run.resultText}
              defaultMode="md"
              className="text-sm text-ink"
            />
          ) : (
            <p className="text-xs text-ink-faint">
              {run.finished ? 'Нет текстового результата.' : 'Ожидание результата…'}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
