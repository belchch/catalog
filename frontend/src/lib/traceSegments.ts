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
const DEPTH_RE = /"depth"\s*:\s*(\d+)/
const ERROR_RE = /"error"\s*:\s*"((?:\\.|[^"\\])*)"/
const UNKNOWN_TOOL_RE = /unknown tool/i

export type LimiterReason = 'deadline' | 'nested_runs' | 'llm_budget' | 'unavailable'

export interface LimiterBudget {
  llmCallsLeft?: number
  nestedRunsLeft?: number
  neededLlmCalls?: number
  neededNestedRuns?: number
}

export interface SkillToolResultInfo {
  ok?: boolean
  error?: string
  runId?: string
  skillName?: string
  depth?: number
  budget?: LimiterBudget
}

export interface LimiterInfo {
  reason: LimiterReason
  toolName: string
  skillName?: string
  depth?: number
  runId?: string
  llmCallsLeft?: number
  nestedRunsLeft?: number
  neededLlmCalls?: number
  neededNestedRuns?: number
}

function asInt(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function readBudget(raw: unknown): LimiterBudget | undefined {
  if (!isRecord(raw)) return undefined
  const budget: LimiterBudget = {
    llmCallsLeft: asInt(raw.llm_calls_left),
    nestedRunsLeft: asInt(raw.nested_runs_left),
    neededLlmCalls: asInt(raw.needed_llm_calls),
    neededNestedRuns: asInt(raw.needed_nested_runs),
  }
  if (
    budget.llmCallsLeft == null &&
    budget.nestedRunsLeft == null &&
    budget.neededLlmCalls == null &&
    budget.neededNestedRuns == null
  ) {
    return undefined
  }
  return budget
}

function readSkillFields(rec: Record<string, unknown>): SkillToolResultInfo {
  const runId = typeof rec.run_id === 'string' && rec.run_id.length >= 8 ? rec.run_id : undefined
  const skillName = typeof rec.skill_name === 'string' && rec.skill_name.length > 0
    ? rec.skill_name
    : undefined
  const error = typeof rec.error === 'string' ? rec.error : undefined
  const ok = rec.ok === true ? true : rec.ok === false ? false : undefined
  return {
    ok,
    error,
    runId,
    skillName,
    depth: asInt(rec.depth),
    budget: readBudget(rec.budget),
  }
}

function unescapeJsonString(raw: string): string {
  try {
    return JSON.parse(`"${raw}"`) as string
  } catch {
    return raw
  }
}

function readSkillFieldsFromText(text: string): SkillToolResultInfo | null {
  const runMatch = text.match(CHILD_RUN_ID_RE)
  const depthMatch = text.match(DEPTH_RE)
  const errorMatch = text.match(ERROR_RE)
  if (!runMatch && !depthMatch && !errorMatch) return null
  return {
    runId: runMatch?.[1],
    depth: depthMatch ? Number(depthMatch[1]) : undefined,
    error: errorMatch ? unescapeJsonString(errorMatch[1]) : undefined,
  }
}

export function parseSkillToolResult(result: unknown): SkillToolResultInfo | null {
  if (isRecord(result)) return readSkillFields(result)
  if (typeof result !== 'string') return null
  try {
    const parsed: unknown = JSON.parse(result)
    if (isRecord(parsed)) return readSkillFields(parsed)
    return null
  } catch {
    return readSkillFieldsFromText(result)
  }
}

function unknownToolIn(result: unknown): boolean {
  if (typeof result === 'string') return UNKNOWN_TOOL_RE.test(result)
  if (isRecord(result) && typeof result.error === 'string') {
    return UNKNOWN_TOOL_RE.test(result.error)
  }
  return false
}

export function detectLimiterReason(
  toolName: string,
  ok: boolean | undefined,
  parsed: SkillToolResultInfo | null,
  result: unknown,
): LimiterReason | null {
  const error = parsed?.error
  if (error === 'deadline exceeded') return 'deadline'
  if (error === 'budget exhausted') {
    const left = parsed?.budget?.nestedRunsLeft
    const needed = parsed?.budget?.neededNestedRuns
    if (typeof left === 'number' && typeof needed === 'number' && left < needed) {
      return 'nested_runs'
    }
    return 'llm_budget'
  }
  if (ok === false && toolName.startsWith('skill_') && unknownToolIn(result)) {
    return 'unavailable'
  }
  return null
}

export function buildLimiterInfo(
  reason: LimiterReason,
  toolName: string,
  parsed: SkillToolResultInfo | null,
  runId?: string,
): LimiterInfo {
  return {
    reason,
    toolName,
    skillName: parsed?.skillName,
    depth: parsed?.depth,
    runId: runId ?? parsed?.runId,
    llmCallsLeft: parsed?.budget?.llmCallsLeft,
    nestedRunsLeft: parsed?.budget?.nestedRunsLeft,
    neededLlmCalls: parsed?.budget?.neededLlmCalls,
    neededNestedRuns: parsed?.budget?.neededNestedRuns,
  }
}

export function attachSkillToolFields(
  toolName: string,
  ok: boolean | undefined,
  result: unknown,
): Pick<RunStep, 'skillDepth' | 'limiter' | 'childRunId'> {
  const parsed = parseSkillToolResult(result)
  const childRunId = toolName.startsWith('skill_') ? parsed?.runId : undefined
  const reason = detectLimiterReason(toolName, ok, parsed, result)
  return {
    skillDepth: parsed?.depth,
    childRunId,
    limiter: reason ? buildLimiterInfo(reason, toolName, parsed, childRunId) : undefined,
  }
}

export function limiterReason(step: RunStep): LimiterReason | null {
  if (step.kind !== 'tool_result') return null
  if (step.limiter) return step.limiter.reason
  return detectLimiterReason(
    step.toolName ?? '',
    step.ok,
    parseSkillToolResult(step.result),
    step.result,
  )
}

export function extractChildRunId(name: string, result: unknown): string | null {
  if (!name.startsWith('skill_')) return null
  return parseSkillToolResult(result)?.runId ?? null
}

export function pluralRu(n: number, forms: [string, string, string]): string {
  const n10 = n % 10
  const n100 = n % 100
  if (n10 === 1 && n100 !== 11) return forms[0]
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return forms[1]
  return forms[2]
}

export function llmCostLabel(n: number): string {
  if (n === 0) return 'без LLM-вызовов'
  return `${n} ${pluralRu(n, ['LLM-вызов', 'LLM-вызова', 'LLM-вызовов'])}`
}

export function limiterTitle(reason: LimiterReason): string {
  if (reason === 'llm_budget') return 'Бюджет LLM-вызовов на ход исчерпан'
  if (reason === 'nested_runs') return 'Лимит вложенных запусков на ход исчерпан'
  if (reason === 'deadline') return 'Время хода вышло'
  return 'Скилл не предлагался модели'
}

export function limiterExplanation(info: LimiterInfo): string {
  const name = info.skillName || info.toolName
  if (info.reason === 'llm_budget') {
    const needed = info.neededLlmCalls
    const left = info.llmCallsLeft
    if (needed != null && left != null) {
      return `Скиллу «${name}» нужно до ${needed} ${pluralRu(needed, ['вызов', 'вызова', 'вызовов'])}, а на ход осталось ${left}. Запуск не начинался.`
    }
    return `Скилл «${name}» не запускался: на ход не осталось LLM-вызовов.`
  }
  if (info.reason === 'nested_runs') {
    return `Ход уже израсходовал все вложенные запуски скиллов. Скилл «${name}» не запускался.`
  }
  if (info.reason === 'deadline') {
    return 'Ход шёл слишком долго, поэтому новые запуски скиллов остановлены.'
  }
  return `Инструмента «${info.toolName}» в этом запуске не было: на такой глубине вложенные скиллы не подключаются либо скилл уже есть в текущей цепочке вызовов.`
}

export function limiterRemainder(info: LimiterInfo): string | null {
  if (info.llmCallsLeft == null || info.nestedRunsLeft == null) return null
  const llm = `${info.llmCallsLeft} ${pluralRu(info.llmCallsLeft, ['вызов', 'вызова', 'вызовов'])}`
  const runs = `${info.nestedRunsLeft} ${pluralRu(info.nestedRunsLeft, ['запуск', 'запуска', 'запусков'])}`
  let line = `Остаток хода: ${llm} · ${runs}`
  if (info.depth != null) line += ` · глубина ${info.depth}`
  return line
}

export function limiterCopy(info: LimiterInfo): {
  title: string
  explanation: string
  remainder: string | null
} {
  return {
    title: limiterTitle(info.reason),
    explanation: limiterExplanation(info),
    remainder: limiterRemainder(info),
  }
}

export function nestedRunCost(trace: unknown[] | null): number | null {
  if (!trace) return null
  let n = 0
  for (const raw of trace) {
    if (entryData(raw).kind === 'llm') n += 1
  }
  return n
}

export function traceSkillDepth(trace: unknown[] | null): number | undefined {
  if (!trace) return undefined
  for (const raw of trace) {
    const { kind, data } = entryData(raw)
    if (kind !== 'skill_pin') continue
    const depth = asInt(data.depth)
    if (depth != null) return depth
  }
  return undefined
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
  | {
      kind: 'limiter'
      limiter: LimiterInfo
      input?: string
      result: RunStep
    }

function takeMatchingCall(out: TraceItemNode[], toolName: string | undefined): string | undefined {
  const prev = out[out.length - 1]
  if (
    prev?.kind === 'item' &&
    prev.item.kind === 'tool_call' &&
    prev.item.toolName === toolName
  ) {
    out.pop()
    return prev.item.input || undefined
  }
  return undefined
}

function stepLimiter(item: RunStep): LimiterInfo | undefined {
  if (item.limiter) return item.limiter
  return attachSkillToolFields(item.toolName ?? '', item.ok, item.result).limiter
}

export function foldNestedRuns(
  items: RunStep[],
  options?: { foldRuns?: boolean },
): TraceItemNode[] {
  const foldRuns = options?.foldRuns !== false
  const out: TraceItemNode[] = []
  for (const item of items) {
    if (item.kind === 'tool_result') {
      const limiter = stepLimiter(item)
      if (limiter) {
        const input = takeMatchingCall(out, item.toolName)
        out.push({ kind: 'limiter', limiter, input, result: item })
        continue
      }
      const childRunId =
        item.childRunId ?? extractChildRunId(item.toolName ?? '', item.result)
      if (foldRuns && childRunId) {
        const input = takeMatchingCall(out, item.toolName)
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
      const ok = data.ok === true
      const fields = attachSkillToolFields(name, ok, data.result)
      return {
        id,
        kind: 'tool_result',
        text: `← ${name}`,
        ok,
        result: formatToolResult(data.result),
        toolName: name,
        childRunId: fields.childRunId,
        skillDepth: fields.skillDepth,
        limiter: fields.limiter,
        stepId,
      }
    }
    if (kind === 'budget') {
      const leftLlm = asInt(data.llm_calls_left)
      const leftRuns = asInt(data.nested_runs_left)
      let text = 'Ограничитель: бюджет хода исчерпан'
      if (leftLlm != null && leftRuns != null) {
        text += ` · осталось ${leftLlm} ${pluralRu(leftLlm, ['вызов', 'вызова', 'вызовов'])}, ${leftRuns} ${pluralRu(leftRuns, ['запуск', 'запуска', 'запусков'])}`
      }
      return { id, kind: 'step', text, stepId }
    }
    if (kind === 'deadline') {
      return { id, kind: 'step', text: 'Ограничитель: время хода вышло', stepId }
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
