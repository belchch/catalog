import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { UseRunStreamResult } from '../hooks/useRunStream.ts'
import { TraceSteps } from './TraceSteps.tsx'

interface RunViewProps {
  run: UseRunStreamResult
  runId: string | null
  onClose: () => void
}

export function RunView({ run, runId, onClose }: RunViewProps) {
  const statusOk = run.status === 'ok'
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
        <button
          className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300"
          onClick={onClose}
        >
          ← К чату
        </button>
      </div>
      <div className="grid flex-1 grid-cols-1 gap-3 overflow-hidden p-3 md:grid-cols-2">
        <div className="overflow-y-auto rounded-md border border-slate-800 bg-slate-900/40 p-3">
          <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">Лента шагов</h3>
          <TraceSteps steps={run.steps} />
          {run.error && <p className="mt-2 text-xs text-red-400">Ошибка: {run.error}</p>}
          {run.closed && !run.finished && (
            <p className="mt-2 text-xs text-amber-400">Соединение закрыто</p>
          )}
        </div>
        <div className="overflow-y-auto rounded-md border border-slate-800 bg-slate-900/40 p-3">
          <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">Результат</h3>
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
