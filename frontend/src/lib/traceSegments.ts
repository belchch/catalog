import type { RunStep } from '../hooks/useRunStream.ts'
import { formatToolArgs, formatToolResult, type VerifyCheckOutcome } from '../ws.ts'

export function toCheckOutcomes(raw: unknown): VerifyCheckOutcome[] | undefined {
  if (!Array.isArray(raw) || raw.length === 0) return undefined
  const out: VerifyCheckOutcome[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) continue
    const rec = item as Record<string, unknown>
    if (typeof rec.check !== 'string' || rec.check.length === 0) continue
    const params =
      rec.params && typeof rec.params === 'object' && !Array.isArray(rec.params)
        ? (rec.params as Record<string, unknown>)
        : {}
    out.push({
      check: rec.check,
      params,
      passed: rec.passed === true,
      reason: typeof rec.reason === 'string' ? rec.reason : null,
      source: typeof rec.source === 'string' ? rec.source : 'builtin',
      skipped: rec.skipped === true,
    })
  }
  return out.length > 0 ? out : undefined
}

export function joinCheckParams(params: Record<string, unknown>): string {
  const parts: string[] = []
  for (const [key, value] of Object.entries(params)) {
    const formatted =
      value !== null && typeof value === 'object'
        ? formatToolArgs(value as Record<string, unknown>)
        : String(value)
    parts.push(`${key}=${formatted}`)
  }
  return parts.join(', ')
}

export function formatCheckParams(params: Record<string, unknown>): string {
  const full = joinCheckParams(params)
  if (full.length > 80) return `${full.slice(0, 80)}…`
  return full
}

const CHILD_RUN_ID_RE = /"run_id"\s*:\s*"([0-9a-f]{8,})"/i

export function extractChildRunId(name: string, result: unknown): string | null {
  if (!name.startsWith('skill_')) return null
  if (result && typeof result === 'object' && !Array.isArray(result)) {
    const id = (result as { run_id?: unknown }).run_id
    return typeof id === 'string' && id.length >= 8 ? id : null
  }
  if (typeof result !== 'string') return null
  try {
    const parsed: unknown = JSON.parse(result)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const id = (parsed as { run_id?: unknown }).run_id
      if (typeof id === 'string' && id.length >= 8) return id
    }
    return null
  } catch {
    const match = result.match(CHILD_RUN_ID_RE)
    return match?.[1] ?? null
  }
}

export function extractToolInput(args: unknown): string {
  if (!args || typeof args !== 'object' || Array.isArray(args)) return ''
  const rec = args as Record<string, unknown>
  if (typeof rec.text === 'string') return rec.text
  if (Array.isArray(rec.texts)) {
    const parts = rec.texts.filter((t): t is string => typeof t === 'string')
    if (parts.length > 0) return parts.join('\n\n---\n\n')
  }
  return formatToolArgs(rec)
}

export type TraceItemNode =
  | { kind: 'item'; item: RunStep }
  | {
      kind: 'run'
      runId: string
      toolName: string
      input?: string
      ok: boolean
      result: RunStep
    }

export function foldNestedRuns(items: RunStep[]): TraceItemNode[] {
  const out: TraceItemNode[] = []
  for (const item of items) {
    const childRunId =
      item.kind === 'tool_result'
        ? (item.childRunId ?? extractChildRunId(item.toolName ?? '', item.result))
        : null
    if (item.kind === 'tool_result' && childRunId) {
      const prev = out[out.length - 1]
      let input: string | undefined
      if (
        prev?.kind === 'item' &&
        prev.item.kind === 'tool_call' &&
        prev.item.toolName === item.toolName
      ) {
        out.pop()
        const fromStep = prev.item.input
        input = fromStep || undefined
      }
      out.push({
        kind: 'run',
        runId: childRunId,
        toolName: item.toolName ?? '',
        input,
        ok: item.ok === true,
        result: item,
      })
      continue
    }
    out.push({ kind: 'item', item })
  }
  return out
}

function entryData(raw: unknown): {
  kind: string
  iteration: number | undefined
  data: Record<string, unknown>
} {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return { kind: 'unknown', iteration: undefined, data: {} }
  }
  const rec = raw as { kind?: unknown; iteration?: unknown; data?: unknown }
  const data =
    rec.data && typeof rec.data === 'object' && !Array.isArray(rec.data)
      ? (rec.data as Record<string, unknown>)
      : {}
  return {
    kind: typeof rec.kind === 'string' ? rec.kind : 'unknown',
    iteration: typeof rec.iteration === 'number' ? rec.iteration : undefined,
    data,
  }
}

export function runTraceToSteps(
  trace: unknown[] | null,
  runId: string,
): RunStep[] {
  if (!trace) return []
  return trace.map((raw, index) => {
    const { kind, iteration, data } = entryData(raw)
    const id = `nested-${runId}-${index}`
    const stepId = typeof data.step_id === 'string' ? data.step_id : undefined
    if (kind === 'script') {
      const ok = data.ok === true
      const chars = data.chars
      let text = ok ? 'Скрипт: готово' : 'Скрипт: ошибка'
      if (typeof chars === 'number') text += ` · ${chars} симв.`
      return {
        id,
        kind: 'script',
        stage: ok ? 'done' : 'error',
        text,
        stepId,
      }
    }
    if (kind === 'verify') {
      const failures = Array.isArray(data.failures)
        ? data.failures.map(String)
        : undefined
      return {
        id,
        kind: 'verify',
        text: `Проверка (итерация ${iteration ?? ''})`,
        passed: data.passed === true,
        failures,
        checks: toCheckOutcomes(data.checks),
        iteration,
        stepId,
      }
    }
    if (kind === 'tool_call') {
      const name = typeof data.name === 'string' ? data.name : 'tool'
      const args =
        data.arguments && typeof data.arguments === 'object' && !Array.isArray(data.arguments)
          ? (data.arguments as Record<string, unknown>)
          : {}
      const input = extractToolInput(args)
      return {
        id,
        kind: 'tool_call',
        text: `→ ${name}(${formatToolArgs(args)})`,
        toolName: name,
        input: input || undefined,
        stepId,
      }
    }
    if (kind === 'tool_result') {
      const name = typeof data.name === 'string' ? data.name : 'tool'
      return {
        id,
        kind: 'tool_result',
        text: `← ${name}`,
        ok: data.ok === true,
        result: formatToolResult(data.result),
        toolName: name,
        childRunId: extractChildRunId(name, data.result) ?? undefined,
        stepId,
      }
    }
    if (kind === 'error') {
      return {
        id,
        kind: 'script',
        stage: 'error',
        text: 'Ошибка',
        error: typeof data.error === 'string' ? data.error : undefined,
        stepId,
      }
    }
    if (kind === 'llm') {
      return {
        id,
        kind: 'step',
        text: `Итерация ${iteration ?? ''}`,
        iteration,
        stepId,
      }
    }
    if (kind === 'skill_pin') {
      const hash = typeof data.config_hash === 'string' ? data.config_hash : ''
      return {
        id,
        kind: 'step',
        text: `пин конфига · ${hash}`,
        stepId,
      }
    }
    return { id, kind: 'step', text: kind, stepId }
  })
}

export type TraceSegment =
  | { kind: 'flat'; item: RunStep }
  | { kind: 'group'; stepId: string; items: RunStep[] }

export function segmentTraceSteps(steps: RunStep[]): TraceSegment[] {
  const segments: TraceSegment[] = []
  for (const item of steps) {
    const stepId = item.stepId?.trim()
    if (!stepId) {
      segments.push({ kind: 'flat', item })
      continue
    }
    const last = segments[segments.length - 1]
    if (last?.kind === 'group' && last.stepId === stepId) {
      last.items.push(item)
    } else {
      segments.push({ kind: 'group', stepId, items: [item] })
    }
  }
  return segments
}

export type TraceGroupStatus = 'ok' | 'error' | 'running'

export function traceGroupStatus(
  items: RunStep[],
  isLastGroup: boolean,
  running: boolean,
): TraceGroupStatus {
  const failed = items.some(
    (s) =>
      (s.kind === 'script' && s.stage === 'error') ||
      (s.kind === 'verify' && s.passed === false),
  )
  if (failed) return 'error'
  if (isLastGroup && running) return 'running'
  return 'ok'
}
