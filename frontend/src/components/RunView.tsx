import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { DocumentOut } from '../api.ts'
import type { UseRunStreamResult } from '../hooks/useRunStream.ts'
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
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-slate-800 px-4 py-2">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-slate-200">
            Прогон{runId ? ` ${runId.slice(0, 8)}` : ''}
          </h2>
          {run.status && (
            <span
              className={
                'rounded px-1.5 py-0.5 text-[10px] uppercase ' +
                (statusOk ? 'bg-emerald-600/30 text-emerald-300' : 'bg-red-600/30 text-red-300')
              }
            >
              {run.status}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300"
            onClick={onClose}
          >
            ← К чату
          </button>
          {!run.finished && (
            <button
              className="rounded bg-red-600 px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
              onClick={run.cancel}
              disabled={run.cancelling}
            >
              {run.cancelling ? 'Останавливаю…' : 'Стоп'}
            </button>
          )}
        </div>
      </div>
      <div className="grid flex-1 grid-cols-1 gap-3 overflow-hidden p-3 md:grid-cols-2">
        <div className="overflow-y-auto rounded-md border border-slate-800 bg-slate-900/40 p-3">
          <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">Лента шагов</h3>
          {/* CATALOG-16: run meta header — model/provider/kind/prompt up front. */}
          {run.meta && (
            <div className="mb-2 rounded border border-slate-800 bg-slate-950/40 p-2 font-mono text-[10px] text-slate-400">
              <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                <span>
                  <span className="text-slate-600">model:</span> {run.meta.model}
                </span>
                {run.meta.provider && (
                  <span>
                    <span className="text-slate-600">provider:</span> {run.meta.provider}
                  </span>
                )}
                <span>
                  <span className="text-slate-600">kind:</span> {run.meta.skillKind}
                </span>
                {run.meta.inputDocs.length > 0 && (
                  <span>
                    <span className="text-slate-600">docs:</span> {run.meta.inputDocs.length}
                  </span>
                )}
              </div>
              {run.meta.systemPrompt && (
                <details className="mt-1">
                  <summary className="cursor-pointer text-slate-600">системный промпт</summary>
                  <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words text-slate-500">
                    {run.meta.systemPrompt}
                  </pre>
                </details>
              )}
            </div>
          )}
          <TraceSteps steps={run.steps} />
          {run.error && <p className="mt-2 text-xs text-red-400">Ошибка: {run.error}</p>}
          {run.closed && !run.finished && (
            <p className="mt-2 text-xs text-amber-400">Соединение закрыто</p>
          )}
        </div>
        <div className="overflow-y-auto rounded-md border border-slate-800 bg-slate-900/40 p-3">
          <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">Результат</h3>
          {outputDocId && (
            <p className="mb-2 rounded border border-emerald-800 bg-emerald-950/40 px-2 py-1 text-xs text-emerald-300">
              Документ создан{outputDoc ? `: «${outputDoc.title}»` : ` (id ${outputDocId.slice(0, 8)})`}
            </p>
          )}
          {canSaveResult && (
            <button
              className="mb-2 rounded bg-indigo-600 px-2 py-1 text-xs text-white disabled:opacity-50"
              disabled={savingResult}
              onClick={() => runId && onSaveResult(runId)}
            >
              {savingResult ? 'Сохраняю…' : 'Сохранить как новый документ'}
            </button>
          )}
          {run.resultText ? (
            <div className="run-markdown text-sm text-slate-200">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{run.resultText}</ReactMarkdown>
            </div>
          ) : (
            <p className="text-xs text-slate-500">
              {run.finished ? 'Нет текстового результата.' : 'Ожидание результата…'}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
