import type { RunStep } from '../hooks/useRunStream.ts'

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
