import type { RunStep } from '../hooks/useRunStream.ts'

export function TraceSteps({ steps }: { steps: RunStep[] }) {
  if (steps.length === 0) {
    return <p className="text-xs text-slate-500">Шаги появятся здесь…</p>
  }
  return (
    <ol className="flex flex-col gap-1.5">
      {steps.map((s) => {
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
