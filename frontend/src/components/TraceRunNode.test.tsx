import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, getRun, type RunOut } from '../api.ts'
import type { RunStep } from '../hooks/useRunStream.ts'
import type { VerifyCheckOutcome } from '../ws.ts'
import { TraceRunNode, TraceSteps } from './TraceSteps.tsx'

vi.mock('../api.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api.ts')>()
  return { ...actual, getRun: vi.fn() }
})

afterEach(() => {
  cleanup()
  vi.mocked(getRun).mockReset()
})

const RUN_ID = '4f2a1b3cdeadbeef0123456789abcdef'

function runOut(partial: Partial<RunOut> = {}): RunOut {
  return {
    id: RUN_ID,
    skill_id: 'sk1',
    input_doc_id: null,
    input_doc_ids: [],
    output_doc_id: null,
    status: 'ok',
    trace: [
      { kind: 'script', iteration: 1, data: { ok: true, chars: 5 } },
      { kind: 'verify', iteration: 1, data: { passed: true, failures: [] } },
    ],
    result_text: 'HELLO',
    parent_run_id: 'session',
    ...partial,
  }
}

function renderNode(overrides: Partial<Parameters<typeof TraceRunNode>[0]> = {}) {
  return render(
    <TraceRunNode
      runId={RUN_ID}
      toolName="skill_extract_terms"
      input="hello world"
      ok
      {...overrides}
    />,
  )
}

function openNode() {
  fireEvent.click(screen.getByText('skill_extract_terms'))
}

describe('TraceRunNode', () => {
  beforeEach(() => {
    vi.mocked(getRun).mockResolvedValue(runOut())
  })

  it('stays collapsed and does not fetch until opened', () => {
    renderNode()
    expect(screen.getByText('skill_extract_terms')).toBeTruthy()
    expect(screen.getByText(`· запуск ${RUN_ID.slice(0, 8)}`)).toBeTruthy()
    expect(screen.getByText('ок')).toBeTruthy()
    expect(screen.queryByText('Загружаю запуск…')).toBeNull()
    expect(getRun).not.toHaveBeenCalled()
  })

  it('loads the child run on first open and keeps it on toggle', async () => {
    let resolveRun: (value: RunOut) => void = () => {}
    vi.mocked(getRun).mockReturnValue(
      new Promise<RunOut>((resolve) => {
        resolveRun = resolve
      }),
    )
    renderNode()
    openNode()
    expect(await screen.findByRole('status')).toHaveProperty(
      'textContent',
      'Загружаю запуск…',
    )
    expect(getRun).toHaveBeenCalledTimes(1)
    expect(getRun).toHaveBeenCalledWith(RUN_ID)
    resolveRun(runOut())
    await waitFor(() => {
      expect(screen.getByText('HELLO')).toBeTruthy()
    })
    expect(screen.getByText('✓ проверки пройдены')).toBeTruthy()
    expect(screen.getByText('вложенный запуск · статус ok')).toBeTruthy()
    expect(screen.getByText('hello world')).toBeTruthy()
    expect(screen.getByText('Скрипт: готово · 5 симв.')).toBeTruthy()

    fireEvent.click(screen.getByText('skill_extract_terms'))
    fireEvent.click(screen.getByText('skill_extract_terms'))
    expect(getRun).toHaveBeenCalledTimes(1)
  })

  it('shows an alert with retry on a failed request', async () => {
    vi.mocked(getRun).mockRejectedValueOnce(
      new ApiError(500, 'Internal Server Error', '{"detail":"db down"}'),
    )
    renderNode()
    openNode()
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('db down')
    expect(screen.getByRole('button', { name: 'Повторить' })).toBeTruthy()

    vi.mocked(getRun).mockResolvedValueOnce(runOut())
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }))
    await waitFor(() => {
      expect(screen.getByText('HELLO')).toBeTruthy()
    })
    expect(getRun).toHaveBeenCalledTimes(2)
  })

  it('shows a quiet not-found state without retry', async () => {
    vi.mocked(getRun).mockRejectedValueOnce(
      new ApiError(404, 'Not Found', '{"detail":"run not found"}'),
    )
    renderNode()
    openNode()
    await waitFor(() => {
      expect(screen.getByText('Запуск не найден')).toBeTruthy()
    })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Повторить' })).toBeNull()
  })

  it('shows a refresh action while the child run is still running', async () => {
    vi.mocked(getRun).mockResolvedValueOnce(runOut({ status: 'running', result_text: null }))
    renderNode({ ok: undefined })
    openNode()
    await waitFor(() => {
      expect(screen.getByText('Запуск ещё выполняется')).toBeTruthy()
    })
    expect(screen.getByRole('button', { name: 'Обновить' })).toBeTruthy()
    expect(screen.getByText('выполняется')).toBeTruthy()

    vi.mocked(getRun).mockResolvedValueOnce(runOut())
    fireEvent.click(screen.getByRole('button', { name: 'Обновить' }))
    await waitFor(() => {
      expect(screen.getByText('HELLO')).toBeTruthy()
    })
    expect(getRun).toHaveBeenCalledTimes(2)
  })
})

const CUSTOM_ID = '9f3a1b2c-aaaa-bbbb-cccc-ddddeeeeffff'

function outcome(
  partial: Partial<VerifyCheckOutcome> & Pick<VerifyCheckOutcome, 'check'>,
): VerifyCheckOutcome {
  return {
    params: {},
    passed: false,
    reason: null,
    source: 'builtin',
    skipped: false,
    ...partial,
  }
}

const PASSED_CHECKS: VerifyCheckOutcome[] = [
  outcome({ check: 'non_empty', passed: true }),
  outcome({ check: 'has_section', params: { heading: 'Тезисы' }, passed: true }),
  outcome({ check: 'min_length', params: { min: 10 }, passed: true }),
  outcome({
    check: `custom:${CUSTOM_ID}`,
    passed: false,
    skipped: true,
    source: 'custom',
    reason: 'не запускалась: детерминированные проверки упали',
  }),
]

const FAILED_CHECKS: VerifyCheckOutcome[] = [
  outcome({ check: 'non_empty', passed: true }),
  outcome({
    check: 'min_length',
    params: { min: 500 },
    passed: false,
    reason: '320 символов, нужно 500',
  }),
]

function summaryText(el: Element | null | undefined): string {
  return (el?.textContent ?? '').replace(/\s+/g, ' ').trim()
}

describe('verify check list', () => {
  it('renders a closed N of M summary when checks passed', () => {
    render(
      <TraceSteps
        steps={[
          {
            id: 'v1',
            kind: 'verify',
            text: 'Проверка (итерация 1)',
            passed: true,
            checks: PASSED_CHECKS,
          } satisfies RunStep,
        ]}
      />,
    )
    const details = document.querySelector('details')
    expect(details?.open).toBe(false)
    expect(summaryText(details?.querySelector('summary'))).toBe(
      '✓ 3 из 4 · пропущено 1',
    )
    expect(screen.getByText('non_empty')).toBeTruthy()
    expect(screen.getByText('has_section')).toBeTruthy()
    expect(screen.getByText(/heading=Тезисы/)).toBeTruthy()
    expect(screen.getByText('custom:9f3a1b2c…')).toBeTruthy()
    expect(screen.getByText(/· AI/)).toBeTruthy()
    expect(screen.getAllByText('пропущена').length).toBeGreaterThan(0)
  })

  it('opens the list on failure and shows the reason', () => {
    render(
      <TraceSteps
        steps={[
          {
            id: 'v1',
            kind: 'verify',
            text: 'Проверка (итерация 1)',
            passed: false,
            failures: ['320 символов, нужно 500'],
            checks: FAILED_CHECKS,
          } satisfies RunStep,
        ]}
      />,
    )
    const details = document.querySelector('details')
    expect(details?.open).toBe(true)
    expect(summaryText(details?.querySelector('summary'))).toBe('✗ 1 из 2')
    expect(screen.getByText(/320 символов, нужно 500/)).toBeTruthy()
    expect(screen.getByText('min_length')).toBeTruthy()
    expect(screen.getByText(/min=500/)).toBeTruthy()
  })

  it('keeps the old failures line when checks are absent', () => {
    render(
      <TraceSteps
        steps={[
          {
            id: 'v1',
            kind: 'verify',
            text: 'Проверка (итерация 1)',
            passed: false,
            failures: ['empty', 'too short'],
          } satisfies RunStep,
        ]}
      />,
    )
    expect(screen.getByText('empty; too short')).toBeTruthy()
    expect(screen.queryByText(/из /)).toBeNull()
  })

  it('shows a node summary with checks', async () => {
    vi.mocked(getRun).mockResolvedValueOnce(
      runOut({
        trace: [
          {
            kind: 'verify',
            iteration: 1,
            data: {
              passed: true,
              failures: [],
              checks: PASSED_CHECKS,
            },
          },
        ],
      }),
    )
    renderNode()
    openNode()
    await waitFor(() => {
      expect(
        screen.getByText((_, node) => {
          return (
            node?.tagName === 'SUMMARY' &&
            (node.textContent ?? '').includes('проверки:') &&
            (node.textContent ?? '').includes('3 из 4')
          )
        }),
      ).toBeTruthy()
    })
    expect(screen.queryByText('✓ проверки пройдены')).toBeNull()
  })

  it('uses the last verify passed after a retry', async () => {
    vi.mocked(getRun).mockResolvedValueOnce(
      runOut({
        trace: [
          {
            kind: 'verify',
            iteration: 1,
            data: {
              passed: false,
              failures: ['320 символов, нужно 500'],
              checks: FAILED_CHECKS,
            },
          },
          {
            kind: 'verify',
            iteration: 2,
            data: {
              passed: true,
              failures: [],
              checks: [
                outcome({ check: 'non_empty', passed: true }),
                outcome({ check: 'min_length', params: { min: 10 }, passed: true }),
              ],
            },
          },
        ],
      }),
    )
    renderNode()
    openNode()
    await waitFor(() => {
      expect(
        screen.getByText((_, node) => {
          return (
            node?.tagName === 'SUMMARY' &&
            (node.textContent ?? '').includes('проверки:') &&
            (node.textContent ?? '').includes('2 из 2')
          )
        }),
      ).toBeTruthy()
    })
    const nodeSummary = [...document.querySelectorAll('summary')].find((el) =>
      (el.textContent ?? '').includes('проверки:'),
    )
    expect(summaryText(nodeSummary)).toBe('✓ проверки: 2 из 2')
    expect(nodeSummary?.className).toContain('text-success-ink')
    expect(nodeSummary?.closest('details')?.open).toBe(false)
    expect(screen.queryByText('✗ проверки:')).toBeNull()
  })

  it('keeps the old passed copy when checks are absent', async () => {
    vi.mocked(getRun).mockResolvedValueOnce(runOut())
    renderNode()
    openNode()
    await waitFor(() => {
      expect(screen.getByText('✓ проверки пройдены')).toBeTruthy()
    })
    expect(screen.queryByText(/проверки:/)).toBeNull()
    expect(screen.queryByText(/из /)).toBeNull()
  })

  it('keeps the old failures line on a node without checks', async () => {
    vi.mocked(getRun).mockResolvedValueOnce(
      runOut({
        status: 'failed',
        result_text: null,
        trace: [
          {
            kind: 'verify',
            iteration: 1,
            data: { passed: false, failures: ['boom'] },
          },
        ],
      }),
    )
    renderNode({ ok: false })
    openNode()
    await waitFor(() => {
      expect(screen.getByText('✗ проверки: boom')).toBeTruthy()
    })
    expect(screen.queryByText(/из /)).toBeNull()
  })
})

const CHILD_RUN = '7c1f0ab2deadbeef0123456789abcdef'

function skillResultStep(partial: Partial<RunStep> = {}): RunStep {
  return {
    id: 'r',
    kind: 'tool_result',
    text: '← skill_summary',
    toolName: 'skill_summary',
    ok: true,
    childRunId: RUN_ID,
    skillDepth: 2,
    result: JSON.stringify({
      ok: true,
      run_id: RUN_ID,
      skill_name: 'Сводка',
      depth: 2,
    }),
    ...partial,
  }
}

describe('nested run header and limiter nodes', () => {
  it('shows depth in the run header before the child run is loaded', () => {
    render(
      <TraceSteps
        steps={[
          {
            id: 'c',
            kind: 'tool_call',
            text: '→ skill_summary({})',
            toolName: 'skill_summary',
            input: 'hello',
          },
          skillResultStep(),
        ]}
      />,
    )
    expect(screen.getByText('· глубина 2')).toBeTruthy()
    expect(screen.queryByText(/LLM-вызов/)).toBeNull()
    expect(screen.queryByText('без LLM-вызовов')).toBeNull()
    expect(getRun).not.toHaveBeenCalled()
  })

  it('adds the actual LLM cost after the child run loads', async () => {
    vi.mocked(getRun).mockResolvedValueOnce(
      runOut({
        trace: [
          { kind: 'llm', iteration: 1, data: {} },
          { kind: 'llm', iteration: 2, data: {} },
          { kind: 'llm', iteration: 3, data: {} },
        ],
      }),
    )
    render(
      <TraceSteps
        steps={[
          {
            id: 'c',
            kind: 'tool_call',
            text: '→ skill_summary({})',
            toolName: 'skill_summary',
          },
          skillResultStep(),
        ]}
      />,
    )
    fireEvent.click(screen.getByText('skill_summary'))
    await waitFor(() => {
      expect(screen.getByText('· 3 LLM-вызова')).toBeTruthy()
    })
    expect(screen.getByText('· глубина 2')).toBeTruthy()
  })

  it('shows без LLM-вызовов for a loaded script run and hides cost while in flight', async () => {
    vi.mocked(getRun).mockResolvedValueOnce(
      runOut({ status: 'running', result_text: null, trace: [] }),
    )
    render(
      <TraceSteps
        steps={[
          {
            id: 'c',
            kind: 'tool_call',
            text: '→ skill_summary({})',
            toolName: 'skill_summary',
          },
          skillResultStep(),
        ]}
      />,
    )
    fireEvent.click(screen.getByText('skill_summary'))
    await waitFor(() => {
      expect(screen.getByText('Запуск ещё выполняется')).toBeTruthy()
    })
    expect(screen.queryByText('без LLM-вызовов')).toBeNull()
    expect(screen.queryByText(/LLM-вызов/)).toBeNull()

    vi.mocked(getRun).mockResolvedValueOnce(runOut({ trace: [{ kind: 'script', data: { ok: true } }] }))
    fireEvent.click(screen.getByRole('button', { name: 'Обновить' }))
    await waitFor(() => {
      expect(screen.getByText('· без LLM-вызовов')).toBeTruthy()
    })
  })

  it('renders the four limiter reasons with human copy', () => {
    const budget = {
      llm_calls_left: 6,
      nested_runs_left: 4,
      needed_llm_calls: 24,
      needed_nested_runs: 1,
    }
    render(
      <TraceSteps
        steps={[
          {
            id: 'c1',
            kind: 'tool_call',
            text: '→ skill_summary({})',
            toolName: 'skill_summary',
          },
          skillResultStep({
            id: 'llm',
            ok: false,
            childRunId: undefined,
            result: JSON.stringify({
              ok: false,
              error: 'budget exhausted',
              budget,
              skill_name: 'Сводка',
              depth: 2,
              run_id: CHILD_RUN,
            }),
          }),
          {
            id: 'c2',
            kind: 'tool_call',
            text: '→ skill_summary({})',
            toolName: 'skill_summary',
          },
          skillResultStep({
            id: 'runs',
            ok: false,
            childRunId: undefined,
            result: JSON.stringify({
              ok: false,
              error: 'budget exhausted',
              budget: { ...budget, llm_calls_left: 0, nested_runs_left: 0 },
              skill_name: 'Сводка',
              depth: 2,
              run_id: CHILD_RUN,
            }),
          }),
          {
            id: 'c3',
            kind: 'tool_call',
            text: '→ skill_summary({})',
            toolName: 'skill_summary',
          },
          skillResultStep({
            id: 'dl',
            ok: false,
            childRunId: undefined,
            result: JSON.stringify({
              ok: false,
              error: 'deadline exceeded',
              skill_name: 'Сводка',
              depth: 1,
              run_id: CHILD_RUN,
            }),
          }),
          {
            id: 'c4',
            kind: 'tool_call',
            text: '→ skill_hidden({})',
            toolName: 'skill_hidden',
          },
          {
            id: 'un',
            kind: 'tool_result',
            text: '← skill_hidden',
            toolName: 'skill_hidden',
            ok: false,
            result: "error: unknown tool 'skill_hidden'",
          },
        ]}
      />,
    )
    expect(screen.getByText('Бюджет LLM-вызовов на ход исчерпан')).toBeTruthy()
    expect(screen.getByText('Лимит вложенных запусков на ход исчерпан')).toBeTruthy()
    expect(screen.getByText('Время хода вышло')).toBeTruthy()
    expect(screen.getByText('Скилл не предлагался модели')).toBeTruthy()
    expect(screen.getByText(/нужно до 24 вызова, а на ход осталось 6/)).toBeTruthy()
    expect(
      screen.getByText(/Ход уже израсходовал все вложенные запуски скиллов/),
    ).toBeTruthy()
    expect(
      screen.getByText(/новые запуски скиллов остановлены/),
    ).toBeTruthy()
    expect(
      screen.getByText(/на такой глубине вложенные скиллы не подключаются/),
    ).toBeTruthy()
    expect(screen.getAllByText('ограничитель')).toHaveLength(3)
    expect(screen.getByText('пометка')).toBeTruthy()
    expect(document.body.textContent).not.toMatch(
      /budget exhausted|deadline exceeded|unknown tool/,
    )
    expect(screen.queryByText(/→ skill_summary/)).toBeNull()
    expect(screen.getAllByText(`· запуск ${CHILD_RUN.slice(0, 8)}`)).toHaveLength(3)
  })

  it('keeps a depth suffix on an unfolded nested tool_result and still folds a limiter', () => {
    render(
      <TraceSteps
        depth={1}
        steps={[
          {
            id: 'c',
            kind: 'tool_call',
            text: '→ skill_summary({})',
            toolName: 'skill_summary',
          },
          skillResultStep(),
          {
            id: 'c2',
            kind: 'tool_call',
            text: '→ skill_hidden({})',
            toolName: 'skill_hidden',
          },
          {
            id: 'un',
            kind: 'tool_result',
            text: '← skill_hidden',
            toolName: 'skill_hidden',
            ok: false,
            result: "error: unknown tool 'skill_hidden'",
          },
        ]}
      />,
    )
    expect(screen.getByText('→ skill_summary({})')).toBeTruthy()
    expect(
      screen.getByText((_, node) => {
        return node?.tagName === 'LI' && (node.textContent ?? '').includes('← skill_summary')
      }),
    ).toBeTruthy()
    expect(screen.getByText('· глубина 2')).toBeTruthy()
    expect(screen.queryByText('⤷')).toBeNull()
    expect(screen.getByText('Скилл не предлагался модели')).toBeTruthy()
    expect(screen.queryByText('← skill_hidden')).toBeNull()
  })

  it('reads depth from skill_pin after the child run loads', async () => {
    vi.mocked(getRun).mockResolvedValueOnce(
      runOut({
        trace: [
          { kind: 'skill_pin', data: { config_hash: 'deadbeef', depth: 1 } },
          { kind: 'script', data: { ok: true, chars: 3 } },
        ],
      }),
    )
    renderNode({ skillDepth: undefined, toolName: 'skill_extract_terms' })
    fireEvent.click(screen.getByText('skill_extract_terms'))
    await waitFor(() => {
      expect(screen.getByText('· глубина 1')).toBeTruthy()
    })
  })
})
