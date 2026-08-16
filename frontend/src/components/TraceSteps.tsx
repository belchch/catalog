import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { ApiError, getRun, type RunOut } from '../api.ts'
import type { RunStep } from '../hooks/useRunStream.ts'
import {
  foldNestedRuns,
  runTraceToSteps,
  segmentTraceSteps,
  traceGroupStatus,
  type TraceGroupStatus,
  type TraceItemNode,
} from '../lib/traceSegments.ts'

function eventCountLabel(n: number): string {
  const n10 = n % 10
  const n100 = n % 100
  if (n10 === 1 && n100 !== 11) return `${n} событие`
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return `${n} события`
  return `${n} событий`
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

function nodeList(items: RunStep[], depth: number): TraceItemNode[] {
  if (depth === 0) return foldNestedRuns(items)
  return items.map((item) => ({ kind: 'item' as const, item }))
}

function TraceNodeView({ node, depth }: { node: TraceItemNode; depth: number }) {
  if (node.kind === 'run') {
    return (
      <li>
        <TraceRunNode
          runId={node.runId}
          toolName={node.toolName}
          input={node.input}
          ok={node.ok}
          depth={depth}
        />
      </li>
    )
  }
  return <TraceItem s={node.item} />
}

function TraceStepGroup({
  n,
  stepId,
  items,
  status,
  depth,
}: {
  n: number
  stepId: string
  items: RunStep[]
  status: TraceGroupStatus
  depth: number
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
  const nodes = nodeList(items, depth)
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
          {nodes.map((node) => (
            <TraceNodeView
              key={node.kind === 'run' ? node.result.id : node.item.id}
              node={node}
              depth={depth}
            />
          ))}
        </ol>
      </details>
    </li>
  )
}

function verifyFailuresOf(run: RunOut): string[] {
  if (!run.trace) return []
  const failures: string[] = []
  for (const raw of run.trace) {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) continue
    const entry = raw as { kind?: unknown; data?: unknown }
    if (entry.kind !== 'verify') continue
    const data =
      entry.data && typeof entry.data === 'object' && !Array.isArray(entry.data)
        ? (entry.data as { passed?: unknown; failures?: unknown })
        : null
    if (!data || data.passed !== false) continue
    if (Array.isArray(data.failures)) failures.push(...data.failures.map(String))
  }
  return failures
}

function verifyEntriesCount(run: RunOut): number {
  if (!run.trace) return 0
  return run.trace.filter((raw) => {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return false
    return (raw as { kind?: unknown }).kind === 'verify'
  }).length
}

function runStatusGlyph(run: RunOut | null, ok?: boolean): {
  glyph: string
  cls: string
  word: string
} {
  if (run) {
    if (run.status === 'ok') {
      return { glyph: '✓', cls: 'text-success-ink', word: 'ок' }
    }
    if (run.status === 'failed' || run.status === 'cancelled') {
      return { glyph: '✗', cls: 'text-danger-ink', word: 'ошибка' }
    }
    if (run.status === 'pending' || run.status === 'running') {
      return { glyph: '…', cls: 'text-ink-faint', word: 'выполняется' }
    }
  }
  if (ok === true) return { glyph: '✓', cls: 'text-success-ink', word: 'ок' }
  if (ok === false) return { glyph: '✗', cls: 'text-danger-ink', word: 'ошибка' }
  return { glyph: '…', cls: 'text-ink-faint', word: 'выполняется' }
}

export function TraceRunNode({
  runId,
  toolName,
  input,
  ok,
  depth = 0,
  className,
}: {
  runId: string
  toolName: string
  input?: string
  ok?: boolean
  depth?: number
  className?: string
}) {
  const [run, setRun] = useState<RunOut | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [notFound, setNotFound] = useState(false)
  const mountedRef = useRef(true)
  const runIdRef = useRef(runId)
  runIdRef.current = runId

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    setRun(null)
    setError(null)
    setNotFound(false)
    setLoading(false)
  }, [runId])

  const load = useCallback(async () => {
    const requested = runId
    setLoading(true)
    setError(null)
    setNotFound(false)
    try {
      const data = await getRun(requested)
      if (!mountedRef.current || runIdRef.current !== requested) return
      setRun(data)
    } catch (e: unknown) {
      if (!mountedRef.current || runIdRef.current !== requested) return
      if (e instanceof ApiError && e.status === 404) {
        setNotFound(true)
      } else {
        setError(e instanceof Error ? e : new Error(String(e)))
      }
    } finally {
      if (mountedRef.current && runIdRef.current === requested) {
        setLoading(false)
      }
    }
  }, [runId])

  const onToggle = (e: { currentTarget: HTMLDetailsElement }) => {
    if (e.currentTarget.open && !run && !loading && !error && !notFound) {
      void load()
    }
  }

  const { glyph, cls, word } = runStatusGlyph(run, ok)
  const failures = run ? verifyFailuresOf(run) : []
  const verifyCount = run ? verifyEntriesCount(run) : 0
  const childSteps = run ? runTraceToSteps(run.trace, runId) : []
  const inFlight = run?.status === 'pending' || run?.status === 'running'
  const failed = run?.status === 'failed' || run?.status === 'cancelled'
  const caption =
    run == null
      ? null
      : run.parent_run_id === null
        ? `запуск · статус ${run.status}`
        : `вложенный запуск · статус ${run.status}`

  return (
    <div className={'rounded border border-line bg-surface p-1.5' + (className ? ` ${className}` : '')}>
      <details onToggle={onToggle} aria-busy={loading || undefined}>
        <summary className="flex cursor-pointer items-center gap-2 font-mono text-[11px] text-ink-muted">
          <span aria-hidden="true" className="shrink-0 text-ink-faint">
            ⤷
          </span>
          <span className="min-w-0 truncate" title={toolName}>
            {toolName}
          </span>
          <span className="ml-auto flex shrink-0 items-center gap-1.5 text-ink-faint">
            <span aria-hidden="true" className={cls}>
              {glyph}
            </span>
            <span>· запуск {runId.slice(0, 8)}</span>
          </span>
          <span className="sr-only">{word}</span>
        </summary>
        <div className="mt-1 flex flex-col gap-1.5 border-l border-line pl-3 font-mono text-[11px]">
          {loading && (
            <p role="status" aria-live="polite" className="text-[11px] text-ink-faint">
              Загружаю запуск…
            </p>
          )}
          {notFound && (
            <p className="text-[11px] text-ink-faint">Запуск не найден</p>
          )}
          {error && (
            <div
              role="alert"
              className="rounded bg-danger-soft p-1.5 text-[11px] text-danger-ink"
            >
              <p>{error instanceof ApiError ? error.detail : error.message}</p>
              <button
                type="button"
                className="btn-secondary text-[11px]"
                onClick={() => void load()}
              >
                Повторить
              </button>
            </div>
          )}
          {inFlight && (
            <>
              <p className="text-[11px] text-ink-faint">Запуск ещё выполняется</p>
              <button
                type="button"
                className="btn-secondary text-[11px]"
                onClick={() => void load()}
              >
                Обновить
              </button>
            </>
          )}
          {failed && run && (
            <p className="rounded bg-danger-soft p-1.5 text-danger-ink">
              {failures.length > 0
                ? failures.join('; ')
                : `Запуск завершился со статусом ${run.status}`}
            </p>
          )}
          {run && input ? (
            <details>
              <summary className="cursor-pointer text-ink-faint">вход</summary>
              <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-surface-muted p-1.5 text-ink-muted">
                {input}
              </pre>
            </details>
          ) : null}
          {run && run.result_text ? (
            <details>
              <summary className="cursor-pointer text-ink-faint">результат</summary>
              <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-surface-muted p-1.5 text-success-ink">
                {run.result_text}
              </pre>
            </details>
          ) : null}
          {run && verifyCount > 0 && failures.length > 0 && (
            <p className="text-danger-ink">✗ проверки: {failures.join('; ')}</p>
          )}
          {run && verifyCount > 0 && failures.length === 0 && (
            <p className="text-success-ink">✓ проверки пройдены</p>
          )}
          {run && childSteps.length === 0 && (
            <p className="text-xs text-ink-faint">Шагов нет.</p>
          )}
          {run && childSteps.length > 0 && (
            <TraceSteps steps={childSteps} depth={depth + 1} />
          )}
          {caption && <p className="text-[11px] text-ink-faint">{caption}</p>}
        </div>
      </details>
    </div>
  )
}

export function TraceSteps({
  steps,
  running = false,
  depth = 0,
}: {
  steps: RunStep[]
  running?: boolean
  depth?: number
}) {
  if (steps.length === 0) {
    return <p className="text-xs text-ink-faint">Шаги появятся здесь…</p>
  }
  const segments = segmentTraceSteps(steps)
  const groupTotal = segments.filter((seg) => seg.kind === 'group').length
  let groupN = 0
  const children: ReactNode[] = []
  let i = 0
  while (i < segments.length) {
    const seg = segments[i]
    if (seg.kind === 'group') {
      groupN += 1
      const n = groupN
      children.push(
        <TraceStepGroup
          key={`${seg.stepId}-${n}`}
          n={n}
          stepId={seg.stepId}
          items={seg.items}
          status={traceGroupStatus(seg.items, n === groupTotal, running)}
          depth={depth}
        />,
      )
      i += 1
      continue
    }
    const flats: RunStep[] = []
    while (i < segments.length && segments[i].kind === 'flat') {
      const flat = segments[i]
      if (flat.kind === 'flat') flats.push(flat.item)
      i += 1
    }
    for (const node of nodeList(flats, depth)) {
      children.push(
        <TraceNodeView
          key={node.kind === 'run' ? node.result.id : node.item.id}
          node={node}
          depth={depth}
        />,
      )
    }
  }
  return <ol className="flex flex-col gap-1.5">{children}</ol>
}
