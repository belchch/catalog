import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { RunConnection, ServerEvent } from '../ws.ts'
import { useRunStream } from './useRunStream.ts'

const { connectRun } = vi.hoisted(() => ({
  connectRun: vi.fn(),
}))

vi.mock('../ws.ts', () => ({
  connectRun,
  formatToolArgs: (args: Record<string, unknown>) => JSON.stringify(args),
  formatToolResult: (result: unknown) =>
    typeof result === 'string' ? result : JSON.stringify(result),
}))

interface CapturedConn {
  onEvent: ((e: ServerEvent) => void) | null
  close: ReturnType<typeof vi.fn<() => void>>
  cancel: ReturnType<typeof vi.fn<() => void>>
}

const captured: CapturedConn = {
  onEvent: null,
  close: vi.fn<() => void>(),
  cancel: vi.fn<() => void>(),
}

describe('useRunStream', () => {
  beforeEach(() => {
    connectRun.mockReset()
    captured.onEvent = null
    captured.close = vi.fn<() => void>()
    captured.cancel = vi.fn<() => void>()
    connectRun.mockImplementation(
      (_runId: string, onEvent: (e: ServerEvent) => void): RunConnection => {
        captured.onEvent = onEvent
        return {
          cancel: captured.cancel,
          close: captured.close,
        }
      },
    )
  })

  it('replaces the result preview on each apply token snapshot', () => {
    const { result } = renderHook(() => useRunStream('run-1'))

    act(() => {
      captured.onEvent?.({
        type: 'token',
        delta: 'Just plain text without a heading.',
      })
    })
    expect(result.current.resultText).toBe('Just plain text without a heading.')

    act(() => {
      captured.onEvent?.({
        type: 'token',
        delta: '# Summary\n\nFixed version.',
      })
    })
    expect(result.current.resultText).toBe('# Summary\n\nFixed version.')
  })

  it('keeps a live pipeline skill step in its own group with a child run', () => {
    const child = '7c1f0ab2deadbeef0123456789abcdef'
    const { result } = renderHook(() => useRunStream('run-1'))

    act(() => {
      captured.onEvent?.({
        type: 'tool_call',
        id: 'step-call',
        name: 'Сводка',
        arguments: { text: 'source text' },
        step_id: 'call',
      })
      captured.onEvent?.({
        type: 'tool_result',
        id: 'step-call',
        name: 'Сводка',
        ok: true,
        result: JSON.stringify({
          ok: true,
          status: 'ok',
          run_id: child,
          skill_id: 'sk_7f3',
          skill_name: 'Сводка',
          config_hash: '1a2b3c4dffff',
          depth: 1,
        }),
        step_id: 'call',
      })
    })

    expect(result.current.steps.map((s) => s.stepId)).toEqual(['call', 'call'])
    expect(result.current.steps[1]).toMatchObject({
      kind: 'tool_result',
      toolName: 'Сводка',
      childRunId: child,
      skillDepth: 1,
    })
  })
})
