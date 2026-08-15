import type { DocumentOut } from '../api.ts'
import type { UseRunStreamResult } from '../hooks/useRunStream.ts'
import { MarkdownView } from './MarkdownView.tsx'
import { segmentTraceSteps } from '../lib/traceSegments.ts'
import { TraceSteps } from './TraceSteps.tsx'

interface RunViewProps {
  run: UseRunStreamResult
  runId: string | null
  documents: DocumentOut[]
  onClose: () => void
  // "Сохранить как новый документ" (CATALOG-18, "на экран" mode only).
  onSaveResult: (runId: string) => void
  savingResult: boolean
  // Set right after a successful save so the confirmation shows immediately,
  // before the documents list has had a chance to refresh.
  savedDoc: DocumentOut | null
}

export function RunView({
  run,
  runId,
  documents,
  onClose,
  onSaveResult,
  savingResult,
  savedDoc,
}: RunViewProps) {
  const statusOk = run.status === 'ok'
  const outputDocId = run.outputDocId ?? savedDoc?.id ?? null
  const outputDoc = outputDocId
    ? documents.find((d) => d.id === outputDocId) ?? (savedDoc?.id === outputDocId ? savedDoc : null)
    : null
  const canSaveResult = run.finished && statusOk && !outputDocId && !!run.resultText
  const groupCount = segmentTraceSteps(run.steps).filter((seg) => seg.kind === 'group').length
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
          {/* CATALOG-16: run meta header — model/provider/kind/prompt up front. */}
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
          {outputDocId && (
            <p className="mb-2 rounded border border-success-line bg-success-soft px-2 py-1 text-xs text-success-ink">
              Документ создан{outputDoc ? `: «${outputDoc.title}»` : ` (id ${outputDocId.slice(0, 8)})`}
            </p>
          )}
          {canSaveResult && (
            <button
              type="button"
              className="btn-primary mb-2"
              disabled={savingResult}
              onClick={() => runId && onSaveResult(runId)}
            >
              {savingResult ? 'Сохраняю…' : 'Сохранить как новый документ'}
            </button>
          )}
          {run.resultText ? (
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
