import { describe, expect, it } from 'vitest'
import type { RunStep } from '../hooks/useRunStream.ts'
import {
  extractChildRunId,
  foldNestedRuns,
  formatCheckParams,
  runTraceToSteps,
  segmentTraceSteps,
  toCheckOutcomes,
  traceGroupStatus,
} from '../lib/traceSegments.ts'

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

describe('extractChildRunId', () => {
  const runId = '4f2a1b3cdeadbeef0123456789abcdef'

  it('returns null for non-skill tools', () => {
    expect(extractChildRunId('read_document', { run_id: runId })).toBeNull()
  })

  it('reads run_id from an object payload', () => {
    expect(extractChildRunId('skill_extract_terms', { run_id: runId, text: 'ok' })).toBe(
      runId,
    )
  })

  it('parses run_id from a JSON string', () => {
    expect(
      extractChildRunId(
        'skill_extract_terms',
        JSON.stringify({ ok: true, run_id: runId, text: 'hello' }),
      ),
    ).toBe(runId)
  })

  it('recovers run_id from a truncated JSON string via regexp', () => {
    const truncated = `{"ok":true,"status":"ok","run_id":"${runId}","skill_id":"s1","text":"${'x'.repeat(400)}`
    expect(extractChildRunId('skill_extract_terms', truncated)).toBe(runId)
  })

  it('returns null when run_id is missing', () => {
    expect(extractChildRunId('skill_extract_terms', { ok: false, error: 'provide text' })).toBeNull()
    expect(extractChildRunId('skill_extract_terms', '{"ok":false}')).toBeNull()
  })
})

describe('foldNestedRuns', () => {
  const runId = '4f2a1b3cdeadbeef0123456789abcdef'

  it('folds a skill tool_call + tool_result pair into a run node', () => {
    const call = step({
      id: 'c',
      kind: 'tool_call',
      toolName: 'skill_extract_terms',
      input: 'hello world',
      text: '→ skill_extract_terms({"text":"hello world"})',
    })
    const result = step({
      id: 'r',
      kind: 'tool_result',
      toolName: 'skill_extract_terms',
      childRunId: runId,
      ok: true,
      text: '← skill_extract_terms',
    })
    const nodes = foldNestedRuns([call, result])
    expect(nodes).toHaveLength(1)
    expect(nodes[0]).toMatchObject({
      kind: 'run',
      runId,
      toolName: 'skill_extract_terms',
      input: 'hello world',
      ok: true,
    })
    if (nodes[0].kind === 'run') expect(nodes[0].result).toBe(result)
  })

  it('keeps a flat tool_result without a child run', () => {
    const call = step({
      id: 'c',
      kind: 'tool_call',
      toolName: 'read_document',
      text: '→ read_document({"id":"d1"})',
    })
    const result = step({
      id: 'r',
      kind: 'tool_result',
      toolName: 'read_document',
      ok: true,
      text: '← read_document',
      result: 'doc text',
    })
    expect(foldNestedRuns([call, result])).toEqual([
      { kind: 'item', item: call },
      { kind: 'item', item: result },
    ])
  })

  it('does not merge a nested skill call into a later flat tool_result', () => {
    const skillCall = step({
      id: 'sc',
      kind: 'tool_call',
      toolName: 'skill_extract_terms',
      input: 'a',
    })
    const skillResult = step({
      id: 'sr',
      kind: 'tool_result',
      toolName: 'skill_extract_terms',
      childRunId: runId,
      ok: true,
    })
    const readResult = step({
      id: 'rr',
      kind: 'tool_result',
      toolName: 'read_document',
      ok: true,
      result: 'plain',
    })
    const nodes = foldNestedRuns([skillCall, skillResult, readResult])
    expect(nodes).toHaveLength(2)
    expect(nodes[0]).toMatchObject({ kind: 'run', runId, toolName: 'skill_extract_terms' })
    expect(nodes[1]).toEqual({ kind: 'item', item: readResult })
  })
})

describe('runTraceToSteps', () => {
  const runId = 'abcd1234ef'

  it('maps trace kinds to RunStep fields', () => {
    const steps = runTraceToSteps(
      [
        { kind: 'skill_pin', iteration: 0, data: { config_hash: 'deadbeef' } },
        { kind: 'script', iteration: 1, data: { ok: true, chars: 12 } },
        { kind: 'verify', iteration: 1, data: { passed: true, failures: [] } },
        {
          kind: 'tool_call',
          iteration: 1,
          data: { name: 'read_document', arguments: { id: 'd1' }, step_id: 'extract' },
        },
        {
          kind: 'tool_result',
          iteration: 1,
          data: { name: 'read_document', ok: true, result: 'hi', step_id: 'extract' },
        },
        { kind: 'llm', iteration: 2, data: {} },
        { kind: 'error', iteration: 2, data: { error: 'boom' } },
        { kind: 'custom', iteration: 0, data: {} },
      ],
      runId,
    )
    expect(steps[0]).toMatchObject({
      id: `nested-${runId}-0`,
      kind: 'step',
      text: 'пин конфига · deadbeef',
    })
    expect(steps[1]).toMatchObject({
      kind: 'script',
      stage: 'done',
      text: 'Скрипт: готово · 12 симв.',
    })
    expect(steps[2]).toMatchObject({
      kind: 'verify',
      text: 'Проверка (итерация 1)',
      passed: true,
    })
    expect(steps[2].checks).toBeUndefined()
    expect(steps[3]).toMatchObject({
      kind: 'tool_call',
      toolName: 'read_document',
      stepId: 'extract',
    })
    expect(steps[3].text).toContain('→ read_document')
    expect(steps[4]).toMatchObject({
      kind: 'tool_result',
      text: '← read_document',
      ok: true,
      result: 'hi',
    })
    expect(steps[5]).toMatchObject({ kind: 'step', text: 'Итерация 2', iteration: 2 })
    expect(steps[6]).toMatchObject({
      kind: 'script',
      stage: 'error',
      text: 'Ошибка',
      error: 'boom',
    })
    expect(steps[7]).toMatchObject({ kind: 'step', text: 'custom' })
  })

  it('returns an empty list for a null or empty trace', () => {
    expect(runTraceToSteps(null, runId)).toEqual([])
    expect(runTraceToSteps([], runId)).toEqual([])
  })

  it('attaches normalized checks on a verify entry', () => {
    const steps = runTraceToSteps(
      [
        {
          kind: 'verify',
          iteration: 1,
          data: {
            passed: false,
            failures: ['too short'],
            checks: [
              { check: 'non_empty', passed: true },
              { check: 'min_length', passed: false, reason: 'too short' },
            ],
          },
        },
      ],
      runId,
    )
    expect(steps[0].checks).toEqual([
      {
        check: 'non_empty',
        params: {},
        passed: true,
        reason: null,
        source: 'builtin',
        skipped: false,
      },
      {
        check: 'min_length',
        params: {},
        passed: false,
        reason: 'too short',
        source: 'builtin',
        skipped: false,
      },
    ])
  })

  it('leaves checks undefined when the verify entry has none', () => {
    const steps = runTraceToSteps(
      [{ kind: 'verify', iteration: 1, data: { passed: true, failures: [] } }],
      runId,
    )
    expect(steps[0].checks).toBeUndefined()
  })
})

describe('toCheckOutcomes', () => {
  it('normalizes a valid list and skips junk entries', () => {
    expect(
      toCheckOutcomes([
        { check: 'non_empty' },
        { notACheck: true },
        null,
        'x',
        {
          check: 'has_section',
          params: { heading: 'X' },
          passed: true,
          reason: 'ok',
          source: 'custom',
          skipped: true,
        },
      ]),
    ).toEqual([
      {
        check: 'non_empty',
        params: {},
        passed: false,
        reason: null,
        source: 'builtin',
        skipped: false,
      },
      {
        check: 'has_section',
        params: { heading: 'X' },
        passed: true,
        reason: 'ok',
        source: 'custom',
        skipped: true,
      },
    ])
  })

  it('returns undefined for missing, empty, or invalid payloads', () => {
    expect(toCheckOutcomes(undefined)).toBeUndefined()
    expect(toCheckOutcomes([])).toBeUndefined()
    expect(toCheckOutcomes('nope')).toBeUndefined()
    expect(toCheckOutcomes([1, 'x', null, {}, { check: '' }])).toBeUndefined()
  })

  it('coerces params, reason and source defaults', () => {
    expect(
      toCheckOutcomes([
        {
          check: 'regex_matches',
          params: ['not-an-object'],
          passed: 'yes',
          reason: 12,
          source: 0,
          skipped: 1,
        },
      ]),
    ).toEqual([
      {
        check: 'regex_matches',
        params: {},
        passed: false,
        reason: null,
        source: 'builtin',
        skipped: false,
      },
    ])
  })
})

describe('formatCheckParams', () => {
  it('returns an empty string for empty params', () => {
    expect(formatCheckParams({})).toBe('')
  })

  it('joins key=value pairs', () => {
    expect(formatCheckParams({ heading: 'Тезисы' })).toBe('heading=Тезисы')
    expect(formatCheckParams({ min: 500, unit: 'chars' })).toBe('min=500, unit=chars')
  })

  it('stringifies objects via formatToolArgs', () => {
    expect(formatCheckParams({ schema: { type: 'string' } })).toBe(
      'schema={"type":"string"}',
    )
  })

  it('truncates signatures longer than 80 characters', () => {
    const result = formatCheckParams({ pattern: 'x'.repeat(100) })
    expect(result.endsWith('…')).toBe(true)
    expect(result.startsWith('pattern=')).toBe(true)
    expect(result.length).toBe(81)
  })
})
