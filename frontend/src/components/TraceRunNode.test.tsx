import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, getRun, type RunOut } from '../api.ts'
import { TraceRunNode } from './TraceSteps.tsx'

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
