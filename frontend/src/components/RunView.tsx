import { useEffect, useState, type KeyboardEvent } from 'react'
import type { DocumentOut } from '../api.ts'
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

function formatCreatedCount(n: number): string {
  const n10 = n % 10
  const n100 = n % 100
  if (n10 === 1 && n100 !== 11) return `Создано ${n} документ`
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return `Создано ${n} документа`
  return `Создано ${n} документов`
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
  const multi = artifacts.length > 1
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

  const active =
    artifacts.find((item) => item.key === activeKey) ?? artifacts[0] ?? null
  const activeIndex = active ? artifacts.indexOf(active) : 0

  const onTabKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!multi) return
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

  const saveLabel = multi ? 'Сохранить как новые документы' : 'Сохранить как новый документ'

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
            <div
              role="status"
              aria-live="polite"
              className="mb-2 rounded border border-success-line bg-success-soft px-2 py-1 text-xs text-success-ink"
            >
              <p>{formatCreatedCount(docIds.length)}</p>
              <p className="mt-1 text-[11px] text-success-ink">Документы прогона</p>
              <div className="mt-1 flex flex-wrap gap-1">
                {docIds.map((id, index) => {
                  const doc = resolveDoc(id, documents, savedDocs, savedDoc)
                  const label = doc?.title || id.slice(0, 8)
                  const full = doc?.title || id
                  const title = index === 0 ? `${full} · основной` : full
                  const cls =
                    (index === 0 ? 'chip-brand ' : 'chip ') +
                    (onOpenDoc ? CHIP_INTERACTIVE : '')
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
          {multi && active ? (
            <>
              <div
                role="tablist"
                aria-label="Результаты прогона"
                className="mb-2 flex flex-wrap gap-1"
                onKeyDown={onTabKeyDown}
              >
                {artifacts.map((item, index) => {
                  const selected = item.key === active.key
                  const tabLabel = item.description?.trim() || item.key
                  const tabTitle = item.description?.trim()
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
              <div className="mb-2 flex items-center gap-2 text-[11px] text-ink-faint">
                <span className="font-mono text-ink">{active.key}</span>
                {activeIndex === 0 && <span className="badge-neutral">основной</span>}
              </div>
              <div
                role="tabpanel"
                id={`run-panel-${active.key}`}
                aria-labelledby={`run-tab-${active.key}`}
                tabIndex={0}
              >
                {active.text ? (
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
