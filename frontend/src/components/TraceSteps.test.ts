import { describe, expect, it } from 'vitest'
import type { RunStep } from '../hooks/useRunStream.ts'
import {
  attachSkillToolFields,
  extractChildRunId,
  foldNestedRuns,
  formatCheckParams,
  limiterCopy,
  limiterReason,
  llmCostLabel,
  nestedRunCost,
  parseSkillToolResult,
  pluralRu,
  runTraceToSteps,
  segmentTraceSteps,
  toCheckOutcomes,
  traceGroupStatus,
  traceSkillDepth,
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

  it('folds a limiter pair on every level and keeps runs unfolded when foldRuns is false', () => {
    const call = step({
      id: 'c',
      kind: 'tool_call',
      toolName: 'skill_summary',
      input: 'hello',
    })
    const limiter = step({
      id: 'r',
      kind: 'tool_result',
      toolName: 'skill_summary',
      ok: false,
      result: JSON.stringify({
        ok: false,
        error: 'deadline exceeded',
        skill_name: 'Сводка',
        depth: 2,
        run_id: runId,
      }),
    })
    const success = step({
      id: 'ok',
      kind: 'tool_result',
      toolName: 'skill_extract_terms',
      childRunId: runId,
      ok: true,
    })
    const folded = foldNestedRuns([call, limiter, success], { foldRuns: false })
    expect(folded).toHaveLength(2)
    expect(folded[0]).toMatchObject({
      kind: 'limiter',
      limiter: { reason: 'deadline', runId, toolName: 'skill_summary' },
      input: 'hello',
    })
    expect(folded[1]).toEqual({ kind: 'item', item: success })
    expect(foldNestedRuns([success], { foldRuns: true })[0]).toMatchObject({
      kind: 'run',
      runId,
    })
  })

  it('folds unavailable even without a child run', () => {
    const call = step({
      id: 'c',
      kind: 'tool_call',
      toolName: 'skill_hidden',
    })
    const result = step({
      id: 'r',
      kind: 'tool_result',
      toolName: 'skill_hidden',
      ok: false,
      result: "error: unknown tool 'skill_hidden'",
    })
    const nodes = foldNestedRuns([call, result])
    expect(nodes).toHaveLength(1)
    expect(nodes[0]).toMatchObject({
      kind: 'limiter',
      limiter: { reason: 'unavailable', toolName: 'skill_hidden' },
    })
    if (nodes[0].kind === 'limiter') expect(nodes[0].limiter.runId).toBeUndefined()
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

  it('maps budget and deadline entries to human limiter text', () => {
    const steps = runTraceToSteps(
      [
        {
          kind: 'budget',
          iteration: 0,
          data: {
            error: 'budget exhausted',
            llm_calls_left: 6,
            nested_runs_left: 4,
            needed_llm_calls: 24,
            needed_nested_runs: 1,
          },
        },
        { kind: 'deadline', iteration: 2, data: { error: 'deadline exceeded' } },
      ],
      runId,
    )
    expect(steps[0].text).toBe(
      'Ограничитель: бюджет хода исчерпан · осталось 6 вызовов, 4 запуска',
    )
    expect(steps[1].text).toBe('Ограничитель: время хода вышло')
    expect(steps.map((s) => s.text).join(' ')).not.toMatch(
      /budget exhausted|deadline exceeded|\bbudget\b/,
    )
  })

  it('attaches depth and limiter on a skill tool_result', () => {
    const child = '4f2a1b3cdeadbeef0123456789abcdef'
    const steps = runTraceToSteps(
      [
        {
          kind: 'tool_result',
          iteration: 1,
          data: {
            name: 'skill_summary',
            ok: true,
            result: { ok: true, run_id: child, depth: 2, skill_name: 'Сводка' },
          },
        },
        {
          kind: 'tool_result',
          iteration: 1,
          data: {
            name: 'skill_summary',
            ok: false,
            result: {
              ok: false,
              error: 'deadline exceeded',
              skill_name: 'Сводка',
              depth: 1,
              run_id: child,
            },
          },
        },
      ],
      runId,
    )
    expect(steps[0]).toMatchObject({
      skillDepth: 2,
      childRunId: child,
    })
    expect(steps[0].limiter).toBeUndefined()
    expect(steps[1].limiter).toMatchObject({ reason: 'deadline', depth: 1 })
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

describe('parseSkillToolResult', () => {
  const runId = '4f2a1b3cdeadbeef0123456789abcdef'

  it('reads depth and skill_name from an object payload', () => {
    expect(
      parseSkillToolResult({
        ok: true,
        run_id: runId,
        skill_name: 'Сводка',
        depth: 2,
        text: 'ok',
      }),
    ).toMatchObject({
      ok: true,
      runId,
      skillName: 'Сводка',
      depth: 2,
    })
  })

  it('reads depth from a truncated JSON string via regexp', () => {
    const truncated = `{"ok":true,"status":"ok","run_id":"${runId}","skill_id":"s1","skill_name":"Сводка","depth":2,"text":"${'x'.repeat(400)}`
    expect(parseSkillToolResult(truncated)).toMatchObject({
      runId,
      depth: 2,
    })
  })

  it('reads budget fields from a short refusal payload', () => {
    expect(
      parseSkillToolResult({
        ok: false,
        error: 'budget exhausted',
        budget: {
          llm_calls_left: 6,
          nested_runs_left: 4,
          needed_llm_calls: 24,
          needed_nested_runs: 1,
        },
        skill_name: 'Сводка',
        depth: 2,
        run_id: runId,
      }),
    ).toMatchObject({
      error: 'budget exhausted',
      skillName: 'Сводка',
      depth: 2,
      runId,
      budget: {
        llmCallsLeft: 6,
        nestedRunsLeft: 4,
        neededLlmCalls: 24,
        neededNestedRuns: 1,
      },
    })
  })

  it('returns null for unrelated values', () => {
    expect(parseSkillToolResult(null)).toBeNull()
    expect(parseSkillToolResult(12)).toBeNull()
    expect(parseSkillToolResult('error: provide text or texts')).toBeNull()
  })
})

describe('limiterReason', () => {
  const runId = '7c1f0ab2deadbeef0123456789abcdef'

  function resultStep(partial: Partial<RunStep>): RunStep {
    return step({
      id: 'r',
      kind: 'tool_result',
      toolName: 'skill_summary',
      ok: false,
      ...partial,
    })
  }

  it('detects deadline', () => {
    const s = resultStep({
      result: JSON.stringify({ ok: false, error: 'deadline exceeded', depth: 1 }),
    })
    expect(limiterReason(s)).toBe('deadline')
  })

  it('detects nested_runs before llm_budget', () => {
    const both = resultStep({
      result: JSON.stringify({
        ok: false,
        error: 'budget exhausted',
        budget: {
          llm_calls_left: 0,
          nested_runs_left: 0,
          needed_llm_calls: 24,
          needed_nested_runs: 1,
        },
      }),
    })
    expect(limiterReason(both)).toBe('nested_runs')
    const llmOnly = resultStep({
      result: JSON.stringify({
        ok: false,
        error: 'budget exhausted',
        budget: {
          llm_calls_left: 6,
          nested_runs_left: 4,
          needed_llm_calls: 24,
          needed_nested_runs: 1,
        },
      }),
    })
    expect(limiterReason(llmOnly)).toBe('llm_budget')
  })

  it('detects unavailable skill tools and ignores other unknown tools', () => {
    expect(
      limiterReason(
        resultStep({ result: "error: unknown tool 'skill_summary'" }),
      ),
    ).toBe('unavailable')
    expect(
      limiterReason(
        resultStep({
          toolName: 'read_document',
          result: "error: unknown tool 'read_document'",
        }),
      ),
    ).toBeNull()
  })

  it('does not treat ordinary skill errors as limiters', () => {
    expect(
      limiterReason(
        resultStep({
          result: JSON.stringify({ ok: false, error: 'provide text or texts', depth: 1 }),
        }),
      ),
    ).toBeNull()
  })

  it('falls back to llm_budget text when budget numbers are missing', () => {
    const s = resultStep({
      result: '{"ok":false,"error":"budget exhausted","depth":2',
    })
    expect(limiterReason(s)).toBe('llm_budget')
    const info = attachSkillToolFields('skill_summary', false, s.result).limiter
    expect(info?.reason).toBe('llm_budget')
    expect(limiterCopy(info!).explanation).toBe(
      'Скилл «skill_summary» не запускался: на ход не осталось LLM-вызовов.',
    )
    expect(limiterCopy(info!).remainder).toBeNull()
  })

  it('builds human copy without error codes', () => {
    const info = attachSkillToolFields('skill_summary', false, {
      ok: false,
      error: 'budget exhausted',
      budget: {
        llm_calls_left: 6,
        nested_runs_left: 4,
        needed_llm_calls: 24,
        needed_nested_runs: 1,
      },
      skill_name: 'Сводка',
      depth: 2,
      run_id: runId,
    }).limiter
    expect(info).toBeTruthy()
    const copy = limiterCopy(info!)
    expect(copy.title).toBe('Бюджет LLM-вызовов на ход исчерпан')
    expect(copy.explanation).toBe(
      'Скиллу «Сводка» нужно до 24 вызова, а на ход осталось 6. Запуск не начинался.',
    )
    expect(copy.remainder).toBe('Остаток хода: 6 вызовов · 4 запуска · глубина 2')
    expect(copy.title + copy.explanation + copy.remainder).not.toMatch(
      /budget exhausted|deadline exceeded|unknown tool/,
    )
  })
})

describe('nestedRunCost and depth helpers', () => {
  it('counts llm entries and treats a missing trace as unknown', () => {
    expect(nestedRunCost(null)).toBeNull()
    expect(nestedRunCost([])).toBe(0)
    expect(
      nestedRunCost([
        { kind: 'llm', iteration: 1, data: {} },
        { kind: 'script', iteration: 1, data: { ok: true } },
        { kind: 'llm', iteration: 2, data: {} },
        { kind: 'llm', iteration: 3, data: {} },
      ]),
    ).toBe(3)
  })

  it('reads depth from skill_pin', () => {
    expect(traceSkillDepth(null)).toBeUndefined()
    expect(
      traceSkillDepth([{ kind: 'skill_pin', data: { config_hash: 'ab', depth: 2 } }]),
    ).toBe(2)
  })

  it('formats cost and plural forms', () => {
    expect(llmCostLabel(0)).toBe('без LLM-вызовов')
    expect(llmCostLabel(1)).toBe('1 LLM-вызов')
    expect(llmCostLabel(3)).toBe('3 LLM-вызова')
    expect(pluralRu(5, ['вызов', 'вызова', 'вызовов'])).toBe('вызовов')
    expect(pluralRu(21, ['вызов', 'вызова', 'вызовов'])).toBe('вызов')
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
