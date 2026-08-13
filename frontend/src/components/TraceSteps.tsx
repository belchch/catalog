import type { RunStep } from '../hooks/useRunStream.ts'

function ScriptStep({ s }: { s: RunStep }) {
  const isError = s.stage === 'error'
  const isDone = s.stage === 'done'
  const dur = s.duration != null ? `${s.duration.toFixed(3)}s` : null
  return (
    <li className="font-mono text-[11px] text-info-ink">
      <span className="mr-1 text-ink-faint">›</span>
      {s.text}
      {dur && <span className="ml-1 text-ink-faint">· {dur}</span>}
      {isError && <span className="ml-1">✗</span>}
      {isDone && <span className="ml-1 text-success-ink">✓</span>}
      {s.snippet && (
        <details className="mt-0.5 pl-3">
          <summary className="cursor-pointer text-ink-faint">код</summary>
          <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-surface-muted p-1.5 text-ink-muted">
            {s.snippet}
          </pre>
        </details>
      )}
      {s.returnValue && (
        <details className="mt-0.5 pl-3">
          <summary className="cursor-pointer text-ink-faint">результат</summary>
          <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-surface-muted p-1.5 text-success-ink">
            {s.returnValue}
          </pre>
        </details>
      )}
      {s.error && (
        <pre className="mt-0.5 ml-3 overflow-x-auto whitespace-pre-wrap break-words rounded bg-danger-soft p-1.5 text-danger-ink">
          {s.error}
        </pre>
      )}
    </li>
  )
}

export function TraceSteps({ steps }: { steps: RunStep[] }) {
  if (steps.length === 0) {
    return <p className="text-xs text-ink-faint">Шаги появятся здесь…</p>
  }
  return (
    <ol className="flex flex-col gap-1.5">
      {steps.map((s) => {
        if (s.kind === 'script') return <ScriptStep key={s.id} s={s} />

        if (s.kind === 'reasoning') {
          return (
            <li key={s.id} className="font-mono text-[11px] italic text-ink-faint">
              <details open>
                <summary className="cursor-pointer not-italic text-ink-faint">
                  💭 рассуждения модели
                </summary>
                <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words pl-3 text-ink-faint">
                  {s.text}
                </pre>
              </details>
            </li>
          )
        }

        const color =
          s.kind === 'tool_result'
            ? s.ok
              ? 'text-success-ink'
              : 'text-danger-ink'
            : s.kind === 'verify'
              ? s.passed
                ? 'text-success-ink'
                : 'text-danger-ink'
              : 'text-ink-muted'
        return (
          <li key={s.id} className={'font-mono text-[11px] ' + color}>
            <span className="mr-1 text-ink-faint">›</span>
            {s.text}
            {s.kind === 'tool_result' && (s.ok ? ' ✓' : ' ✗')}
            {s.kind === 'tool_result' && s.result && (
              <details className="mt-0.5 pl-3">
                <summary className="cursor-pointer text-ink-faint">результат</summary>
                <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-surface-muted p-1.5 text-ink-faint">
                  {s.result}
                </pre>
              </details>
            )}
            {s.kind === 'verify' && !s.passed && s.failures && s.failures.length > 0 && (
              <span className="ml-1 block pl-3 text-danger-ink">
                {s.failures.join('; ')}
              </span>
            )}
          </li>
        )
      })}
    </ol>
  )
}
