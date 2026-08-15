import { useLayoutEffect, useRef, type ReactNode } from 'react'
import type { RunStep } from '../hooks/useRunStream.ts'
import {
  segmentTraceSteps,
  traceGroupStatus,
  type TraceGroupStatus,
} from '../lib/traceSegments.ts'

function eventCountLabel(n: number): string {
  const n10 = n % 10
  const n100 = n % 100
  if (n10 === 1 && n100 !== 11) return `${n} событие`
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return `${n} события`
  return `${n} событий`
}

function parseSkillToolPayload(raw: string | undefined): {
  skillName?: string
  skillId?: string
  configHash?: string
  text?: string
  failures: string[]
  ok: boolean
} | null {
  if (!raw) return null
  try {
    const data = JSON.parse(raw) as Record<string, unknown>
    if (typeof data.skill_id !== 'string') return null
    const failures = Array.isArray(data.verify_failures)
      ? data.verify_failures.map(String)
      : []
    return {
      skillId: data.skill_id,
      skillName: typeof data.skill_name === 'string' ? data.skill_name : undefined,
      configHash: typeof data.config_hash === 'string' ? data.config_hash : undefined,
      text: typeof data.text === 'string' ? data.text : undefined,
      failures,
      ok: data.ok === true || data.status === 'ok',
    }
  } catch {
    return null
  }
}

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

function NestedSkillNode({
  call,
  result,
}: {
  call?: RunStep
  result: RunStep
}) {
  const payload = parseSkillToolPayload(result.result)
  const ok = payload?.ok ?? result.ok
  const title =
    payload?.skillName ||
    call?.text?.replace(/^→\s*/, '') ||
    'Вложенный скилл'
  return (
    <li className="rounded border border-line bg-surface p-1.5">
      <details open>
        <summary className="flex cursor-pointer items-center gap-2 font-mono text-[11px] text-ink-muted">
          <span className="min-w-0 truncate">вызов · {title}</span>
          <span className="ml-auto flex shrink-0 items-center gap-1.5 text-ink-faint">
            <span
              aria-hidden="true"
              className={ok ? 'text-success-ink' : 'text-danger-ink'}
            >
              {ok ? '✓' : '✗'}
            </span>
          </span>
        </summary>
        <ol className="mt-1 flex flex-col gap-1.5 border-l border-line pl-3">
          {payload?.configHash && (
            <li className="font-mono text-[11px] text-ink-faint">
              pinned {payload.configHash}
            </li>
          )}
          {payload?.text != null && (
            <li className="font-mono text-[11px] text-ink-muted">
              <details>
                <summary className="cursor-pointer text-ink-faint">результат</summary>
                <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-surface-muted p-1.5">
                  {payload.text}
                </pre>
              </details>
            </li>
          )}
          {payload && payload.failures.length > 0 && (
            <li className="font-mono text-[11px] text-danger-ink">
              verify: {payload.failures.join('; ')}
            </li>
          )}
        </ol>
      </details>
    </li>
  )
}

function TraceItem({ s }: { s: RunStep }) {
  if (s.kind === 'script') return <ScriptStep s={s} />

  if (s.kind === 'reasoning') {
    return (
      <li className="font-mono text-[11px] italic text-ink-faint">
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
    <li className={'font-mono text-[11px] ' + color}>
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
}

function TraceStepGroup({
  n,
  stepId,
  items,
  status,
}: {
  n: number
  stepId: string
  items: RunStep[]
  status: TraceGroupStatus
}) {
  const detailsRef = useRef<HTMLDetailsElement>(null)
  useLayoutEffect(() => {
    if (detailsRef.current) detailsRef.current.open = true
  }, [])
  const glyph = status === 'error' ? '✗' : status === 'running' ? '…' : '✓'
  const glyphCls =
    status === 'error'
      ? 'text-danger-ink'
      : status === 'running'
        ? 'text-ink-faint'
        : 'text-success-ink'
  const statusWord =
    status === 'error' ? 'ошибка' : status === 'running' ? 'выполняется' : 'ок'
  return (
    <li className="rounded border border-line bg-surface p-1.5">
      <details ref={detailsRef}>
        <summary className="flex cursor-pointer items-center gap-2 font-mono text-[11px] text-ink-muted">
          <span className="min-w-0 truncate">
            шаг {n} · {stepId}
          </span>
          <span className="ml-auto flex shrink-0 items-center gap-1.5 text-ink-faint">
            <span aria-hidden="true" className={glyphCls}>
              {glyph}
            </span>
            <span>{eventCountLabel(items.length)}</span>
          </span>
          <span className="sr-only">{statusWord}</span>
        </summary>
        <ol className="mt-1 flex flex-col gap-1.5 border-l border-line pl-3">
          {renderStepList(items)}
        </ol>
      </details>
    </li>
  )
}

function renderStepList(steps: RunStep[]): ReactNode[] {
  const nodes: ReactNode[] = []
  for (let i = 0; i < steps.length; i += 1) {
    const s = steps[i]
    if (s.kind === 'tool_result' && parseSkillToolPayload(s.result) != null) {
      const prev = i > 0 ? steps[i - 1] : undefined
      const call = prev?.kind === 'tool_call' ? prev : undefined
      if (call && nodes.length > 0) {
        nodes.pop()
      }
      nodes.push(<NestedSkillNode key={s.id} call={call} result={s} />)
      continue
    }
    nodes.push(<TraceItem key={s.id} s={s} />)
  }
  return nodes
}

export function TraceSteps({
  steps,
  running = false,
}: {
  steps: RunStep[]
  running?: boolean
}) {
  if (steps.length === 0) {
    return <p className="text-xs text-ink-faint">Шаги появятся здесь…</p>
  }
  const segments = segmentTraceSteps(steps)
  const groupTotal = segments.filter((seg) => seg.kind === 'group').length
  let groupN = 0
  return (
    <ol className="flex flex-col gap-1.5">
      {segments.map((seg) => {
        if (seg.kind === 'flat') {
          const idx = steps.findIndex((s) => s.id === seg.item.id)
          const prev = idx > 0 ? steps[idx - 1] : undefined
          if (
            seg.item.kind === 'tool_result' &&
            parseSkillToolPayload(seg.item.result) != null
          ) {
            const call = prev?.kind === 'tool_call' ? prev : undefined
            return (
              <NestedSkillNode key={seg.item.id} call={call} result={seg.item} />
            )
          }
          if (
            seg.item.kind === 'tool_call' &&
            idx + 1 < steps.length &&
            steps[idx + 1].kind === 'tool_result' &&
            parseSkillToolPayload(steps[idx + 1].result) != null
          ) {
            return null
          }
          return <TraceItem key={seg.item.id} s={seg.item} />
        }
        groupN += 1
        const n = groupN
        return (
          <TraceStepGroup
            key={`${seg.stepId}-${n}`}
            n={n}
            stepId={seg.stepId}
            items={seg.items}
            status={traceGroupStatus(seg.items, n === groupTotal, running)}
          />
        )
      })}
    </ol>
  )
}
