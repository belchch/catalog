import type { RunStep } from '../hooks/useRunStream.ts'

function ScriptStep({ s }: { s: RunStep }) {
  const isError = s.stage === 'error'
  const isDone = s.stage === 'done'
  const dur = s.duration != null ? `${s.duration.toFixed(3)}s` : null
  return (
    <li className="font-mono text-[11px] text-sky-300">
      <span className="mr-1 text-slate-600">›</span>
      {s.text}
      {dur && <span className="ml-1 text-slate-500">· {dur}</span>}
      {isError && <span className="ml-1">✗</span>}
      {isDone && <span className="ml-1 text-emerald-400">✓</span>}
      {s.snippet && (
        <details className="mt-0.5 pl-3">
          <summary className="cursor-pointer text-slate-500">код</summary>
          <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-slate-950/60 p-1.5 text-slate-300">
            {s.snippet}
          </pre>
        </details>
      )}
      {s.returnValue && (
        <details className="mt-0.5 pl-3">
          <summary className="cursor-pointer text-slate-500">результат</summary>
          <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-slate-950/60 p-1.5 text-emerald-200/90">
            {s.returnValue}
          </pre>
        </details>
      )}
      {s.error && (
        <pre className="mt-0.5 ml-3 overflow-x-auto whitespace-pre-wrap break-words rounded bg-red-950/40 p-1.5 text-red-300">
          {s.error}
        </pre>
      )}
    </li>
  )
}

export function TraceSteps({ steps }: { steps: RunStep[] }) {
  if (steps.length === 0) {
    return <p className="text-xs text-slate-500">Шаги появятся здесь…</p>
  }
  return (
    <ol className="flex flex-col gap-1.5">
      {steps.map((s) => {
        if (s.kind === 'script') return <ScriptStep key={s.id} s={s} />

        if (s.kind === 'reasoning') {
          // Reasoning is rendered muted — it is context, not the main output.
          return (
            <li key={s.id} className="font-mono text-[11px] italic text-slate-500">
              <details open>
                <summary className="cursor-pointer not-italic text-slate-600">
                  💭 рассуждения модели
                </summary>
                <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words pl-3 text-slate-500">
                  {s.text}
                </pre>
              </details>
            </li>
          )
        }

        const color =
          s.kind === 'tool_result'
            ? s.ok
              ? 'text-emerald-300'
              : 'text-red-300'
            : s.kind === 'verify'
              ? s.passed
                ? 'text-emerald-300'
                : 'text-red-300'
              : 'text-slate-300'
        return (
          <li key={s.id} className={'font-mono text-[11px] ' + color}>
            <span className="mr-1 text-slate-600">›</span>
            {s.text}
            {s.kind === 'tool_result' && (s.ok ? ' ✓' : ' ✗')}
            {/* CATALOG-16: show the tool's actual return value (collapsible). */}
            {s.kind === 'tool_result' && s.result && (
              <details className="mt-0.5 pl-3">
                <summary className="cursor-pointer text-slate-500">результат</summary>
                <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-slate-950/60 p-1.5 text-slate-400">
                  {s.result}
                </pre>
              </details>
            )}
            {s.kind === 'verify' && !s.passed && s.failures && s.failures.length > 0 && (
              <span className="ml-1 block pl-3 text-red-400/80">
                {s.failures.join('; ')}
              </span>
            )}
          </li>
        )
      })}
    </ol>
  )
}
