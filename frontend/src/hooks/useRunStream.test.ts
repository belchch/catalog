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
})
