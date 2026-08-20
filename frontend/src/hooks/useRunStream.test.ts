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

  it('reads a finish frame without named outputs as a single result', () => {
    const { result } = renderHook(() => useRunStream('run-1'))
    act(() => {
      captured.onEvent?.({
        type: 'finish',
        status: 'ok',
        output_doc_id: 'doc-1',
        result_text: 'HELLO',
      })
    })
    expect(result.current.resultText).toBe('HELLO')
    expect(result.current.outputDocId).toBe('doc-1')
    expect(result.current.outputDocIds).toEqual([])
    expect(result.current.artifacts).toEqual([])
    expect(result.current.finished).toBe(true)
  })

  it('reads named artifacts from finish and uses the primary text', () => {
    const { result } = renderHook(() => useRunStream('run-1'))
    act(() => {
      captured.onEvent?.({
        type: 'finish',
        status: 'ok',
        output_doc_id: 'doc-1',
        output_doc_ids: ['doc-1', 'doc-2'],
        result_text: 'ignored-when-artifacts-present',
        result_artifacts: {
          brief: 'PRIMARY',
          table: 'TABLE',
        },
      })
    })
    expect(result.current.artifacts).toEqual([
      { key: 'brief', text: 'PRIMARY' },
      { key: 'table', text: 'TABLE' },
    ])
    expect(result.current.resultText).toBe('PRIMARY')
    expect(result.current.outputDocIds).toEqual(['doc-1', 'doc-2'])
  })

  it('reads a collection artifact from the dict-shaped result_artifacts (WS wire shape)', () => {
    const { result } = renderHook(() => useRunStream('run-1'))
    act(() => {
      captured.onEvent?.({
        type: 'finish',
        status: 'ok',
        output_doc_id: 'doc-1',
        output_doc_ids: ['doc-1', 'doc-2', 'doc-3'],
        result_text: 'ignored-when-artifacts-present',
        result_artifacts: {
          index: 'INDEX',
          chapters: ['Ch1', 'Ch2'],
        },
      })
    })
    expect(result.current.artifacts).toEqual([
      { key: 'index', text: 'INDEX' },
      { key: 'chapters', text: ['Ch1', 'Ch2'] },
    ])
    expect(result.current.resultText).toBe('INDEX')
    expect(result.current.outputDocIds).toEqual(['doc-1', 'doc-2', 'doc-3'])
  })

  it('joins the primary artifact when it is itself the collection (array-first key)', () => {
    // ADR-0025 Decision 3: outputs[0].multiple is allowed — the primary
    // artifact's own value is an array, so primaryArtifactText must take the
    // Array.isArray branch (not just the string else-branch every other
    // artifact test exercises) and join it with the backend's separator.
    const { result } = renderHook(() => useRunStream('run-1'))
    act(() => {
      captured.onEvent?.({
        type: 'finish',
        status: 'ok',
        output_doc_id: 'doc-1',
        output_doc_ids: ['doc-1', 'doc-2'],
        result_text: 'ignored-when-artifacts-present',
        result_artifacts: {
          chapters: ['Ch1', 'Ch2'],
        },
      })
    })
    expect(result.current.artifacts).toEqual([{ key: 'chapters', text: ['Ch1', 'Ch2'] }])
    expect(result.current.resultText).toBe('Ch1\n\n---\n\nCh2')
    expect(result.current.outputDocIds).toEqual(['doc-1', 'doc-2'])
  })
})
