import { describe, expect, it } from 'vitest'
import type { RunStep } from '../hooks/useRunStream.ts'
import { segmentTraceSteps, traceGroupStatus } from '../lib/traceSegments.ts'

function step(partial: Partial<RunStep> & Pick<RunStep, 'id' | 'kind'>): RunStep {
  return { text: partial.text ?? partial.id, ...partial }
}

describe('segmentTraceSteps', () => {
  it('keeps a flat list when stepId is missing', () => {
    const steps = [
      step({ id: 'a', kind: 'script', text: 'Скрипт: запуск' }),
      step({ id: 'b', kind: 'script', text: 'Скрипт: готово' }),
    ]
    expect(segmentTraceSteps(steps)).toEqual([
      { kind: 'flat', item: steps[0] },
      { kind: 'flat', item: steps[1] },
    ])
  })

  it('groups consecutive events with the same stepId', () => {
    const steps = [
      step({ id: 'a', kind: 'script', stepId: 'extract', text: 'start' }),
      step({ id: 'b', kind: 'script', stepId: 'extract', text: 'done' }),
      step({ id: 'c', kind: 'verify', text: 'Проверка' }),
    ]
    const segs = segmentTraceSteps(steps)
    expect(segs).toHaveLength(2)
    expect(segs[0]).toMatchObject({ kind: 'group', stepId: 'extract' })
    if (segs[0].kind === 'group') expect(segs[0].items).toHaveLength(2)
    expect(segs[1]).toEqual({ kind: 'flat', item: steps[2] })
  })

  it('opens a new group when the same stepId reappears later', () => {
    const steps = [
      step({ id: 'a', kind: 'script', stepId: 'x' }),
      step({ id: 'b', kind: 'script', stepId: 'y' }),
      step({ id: 'c', kind: 'script', stepId: 'x' }),
    ]
    const segs = segmentTraceSteps(steps)
    expect(segs.map((s) => (s.kind === 'group' ? s.stepId : 'flat'))).toEqual([
      'x',
      'y',
      'x',
    ])
  })
})

describe('traceGroupStatus', () => {
  it('marks script error and failed verify as error', () => {
    expect(
      traceGroupStatus(
        [step({ id: 's', kind: 'script', stage: 'error' })],
        true,
        true,
      ),
    ).toBe('error')
    expect(
      traceGroupStatus(
        [step({ id: 'v', kind: 'verify', passed: false })],
        false,
        false,
      ),
    ).toBe('error')
  })

  it('shows running only on the last group', () => {
    const items = [step({ id: 's', kind: 'script', stage: 'start' })]
    expect(traceGroupStatus(items, true, true)).toBe('running')
    expect(traceGroupStatus(items, false, true)).toBe('ok')
    expect(traceGroupStatus(items, true, false)).toBe('ok')
  })
})
