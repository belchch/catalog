import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { DocumentOut, MessageOut } from '../api.ts'
import type { PlannerConnection, ServerEvent } from '../ws.ts'
import { usePlannerSession } from './usePlannerSession.ts'

const {
  getSessionDocuments,
  listSessionMessages,
  getSessionArtifacts,
  connectPlanner,
} = vi.hoisted(() => ({
  getSessionDocuments: vi.fn(),
  listSessionMessages: vi.fn(),
  getSessionArtifacts: vi.fn(),
  connectPlanner: vi.fn(),
}))

vi.mock('../api.ts', () => ({
  getSessionDocuments,
  listSessionMessages,
  getSessionArtifacts,
  patchArtifact: vi.fn(),
  patchSkillMeta: vi.fn(),
  removeSessionDocument: vi.fn(),
}))

vi.mock('../ws.ts', () => ({
  connectPlanner,
  formatToolArgs: (args: Record<string, unknown>) => JSON.stringify(args),
}))

const DOC_A: DocumentOut = {
  id: 'doc-a',
  title: 'Устав',
  kind: 'docx',
  created_at: '2026-01-01T00:00:00Z',
}

const DOC_B: DocumentOut = {
  id: 'doc-b',
  title: 'Отчёт',
  kind: 'md',
  created_at: '2026-01-02T00:00:00Z',
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

interface CapturedConn {
  onEvent: ((e: ServerEvent) => void) | null
  onOpen: (() => void) | undefined
  onClose: (() => void) | undefined
  send: ReturnType<typeof vi.fn>
  close: ReturnType<typeof vi.fn>
  cancel: ReturnType<typeof vi.fn>
}

const captured: CapturedConn = {
  onEvent: null,
  onOpen: undefined,
  onClose: undefined,
  send: vi.fn(),
  close: vi.fn(),
  cancel: vi.fn(),
}

function storedMessage(role: string, content: string, id = 1): MessageOut {
  return {
    id,
    session_id: 's1',
    role,
    content,
    tool_name: null,
    tool_call_id: null,
    created_at: '2026-01-01T00:00:00Z',
  }
}

describe('usePlannerSession', () => {
  beforeEach(() => {
    getSessionDocuments.mockReset()
    listSessionMessages.mockReset()
    getSessionArtifacts.mockReset()
    connectPlanner.mockReset()
    listSessionMessages.mockResolvedValue([])
    getSessionArtifacts.mockResolvedValue([])
    getSessionDocuments.mockResolvedValue([])
    captured.onEvent = null
    captured.onOpen = undefined
    captured.onClose = undefined
    captured.send = vi.fn()
    captured.close = vi.fn()
    captured.cancel = vi.fn()
    connectPlanner.mockImplementation(
      (
        _sessionId: string,
        onEvent: (e: ServerEvent) => void,
        opts?: { onOpen?: () => void; onClose?: () => void },
      ): PlannerConnection => {
        captured.onEvent = onEvent
        captured.onOpen = opts?.onOpen
        captured.onClose = opts?.onClose
        return {
          send: captured.send,
          cancel: captured.cancel,
          close: captured.close,
        } as PlannerConnection
      },
    )
  })

  it('keeps session_docs after a later empty GET', async () => {
    const pending = deferred<DocumentOut[]>()
    getSessionDocuments.mockReturnValue(pending.promise)

    const { result } = renderHook(() => usePlannerSession('s1'))
    expect(connectPlanner).toHaveBeenCalled()

    act(() => {
      captured.onEvent?.({ type: 'session_docs', documents: [DOC_A] })
    })
    expect(result.current.sessionDocuments).toEqual([DOC_A])

    await act(async () => {
      pending.resolve([])
      await pending.promise
    })
    expect(result.current.sessionDocuments).toEqual([DOC_A])
  })

  it('keeps session_docs when an in-flight empty GET resolves after the frame', async () => {
    const pending = deferred<DocumentOut[]>()
    getSessionDocuments.mockReturnValue(pending.promise)

    const { result } = renderHook(() => usePlannerSession('s1'))

    await act(async () => {
      pending.resolve([])
      await pending.promise
    })
    expect(result.current.sessionDocuments).toEqual([])

    act(() => {
      captured.onEvent?.({ type: 'session_docs', documents: [DOC_A] })
    })
    expect(result.current.sessionDocuments).toEqual([DOC_A])
  })

  it('hydrates documents from HTTP when the session changes', async () => {
    getSessionDocuments.mockImplementation((id: string) => {
      if (id === 's1') return Promise.resolve([DOC_A])
      if (id === 's2') return Promise.resolve([DOC_B])
      return Promise.resolve([])
    })

    const { result, rerender } = renderHook(
      ({ id }: { id: string | null }) => usePlannerSession(id),
      { initialProps: { id: 's1' } },
    )

    await waitFor(() => {
      expect(result.current.sessionDocuments).toEqual([DOC_A])
    })

    rerender({ id: 's2' })

    await waitFor(() => {
      expect(result.current.sessionDocuments).toEqual([DOC_B])
    })
  })

  it('merges composer documents into sessionDocuments in the same send()', () => {
    const { result } = renderHook(() => usePlannerSession('s1'))

    act(() => {
      captured.onOpen?.()
      result.current.send('привет', [DOC_A.id, DOC_B.id], [DOC_A, DOC_B])
    })

    expect(result.current.messages.at(-1)).toEqual({
      role: 'user',
      content: 'привет',
    })
    expect(result.current.sessionDocuments).toEqual([DOC_A, DOC_B])
    expect(captured.send).toHaveBeenCalledWith('привет', [DOC_A.id, DOC_B.id])
  })

  it('does not let an empty GET wipe optimistic documents after send()', async () => {
    const pending = deferred<DocumentOut[]>()
    getSessionDocuments.mockReturnValue(pending.promise)

    const { result } = renderHook(() => usePlannerSession('s1'))

    act(() => {
      result.current.send('привет', [DOC_A.id], [DOC_A])
    })
    expect(result.current.sessionDocuments).toEqual([DOC_A])

    await act(async () => {
      pending.resolve([])
      await pending.promise
    })
    expect(result.current.sessionDocuments).toEqual([DOC_A])
  })

  it('does not replace sessionDocuments on finish GET when ids already match', async () => {
    const pending = deferred<DocumentOut[]>()
    getSessionDocuments.mockReturnValue(pending.promise)

    const { result } = renderHook(() => usePlannerSession('s1'))

    act(() => {
      captured.onEvent?.({ type: 'session_docs', documents: [DOC_A] })
    })
    const afterStream = result.current.sessionDocuments
    expect(afterStream).toEqual([DOC_A])

    act(() => {
      captured.onEvent?.({ type: 'finish' })
    })

    const sameIds: DocumentOut[] = [{ ...DOC_A, title: 'Устав (копия)' }]
    await act(async () => {
      pending.resolve(sameIds)
      await pending.promise
    })

    expect(result.current.sessionDocuments).toBe(afterStream)
  })

  it('applies finish GET when document ids differ from session_docs', async () => {
    const pending = deferred<DocumentOut[]>()
    getSessionDocuments.mockReturnValue(pending.promise)

    const { result } = renderHook(() => usePlannerSession('s1'))

    act(() => {
      captured.onEvent?.({ type: 'session_docs', documents: [DOC_A] })
    })

    act(() => {
      captured.onEvent?.({ type: 'finish' })
    })

    await act(async () => {
      pending.resolve([DOC_A, DOC_B])
      await pending.promise
    })

    expect(result.current.sessionDocuments).toEqual([DOC_A, DOC_B])
  })

  it('appends new documents without duplicating existing ones', () => {
    const { result } = renderHook(() => usePlannerSession('s1'))

    act(() => {
      captured.onOpen?.()
      result.current.send('раз', [DOC_A.id], [DOC_A])
    })
    act(() => {
      result.current.send('два', [DOC_A.id, DOC_B.id], [DOC_A, DOC_B])
    })

    expect(result.current.sessionDocuments).toEqual([DOC_A, DOC_B])
  })

  it('clears streaming and cancelling on close and marks the turn interrupted', () => {
    const { result } = renderHook(() => usePlannerSession('s1'))

    act(() => {
      captured.onOpen?.()
      result.current.send('привет')
      result.current.cancel()
    })
    expect(result.current.streaming).toBe(true)
    expect(result.current.cancelling).toBe(true)

    act(() => {
      captured.onClose?.()
    })
    expect(result.current.streaming).toBe(false)
    expect(result.current.cancelling).toBe(false)
    expect(result.current.closed).toBe(true)
    expect(result.current.interrupted).toBe(true)
    expect(result.current.reconnecting).toBe(false)
  })

  it('does not mark a close outside a turn as interrupted', () => {
    const { result } = renderHook(() => usePlannerSession('s1'))

    act(() => {
      captured.onOpen?.()
      captured.onClose?.()
    })
    expect(result.current.closed).toBe(true)
    expect(result.current.interrupted).toBe(false)
    expect(result.current.streaming).toBe(false)
  })

  it('clears streaming when send is queued and the socket closes before open', () => {
    const { result } = renderHook(() => usePlannerSession('s1'))

    act(() => {
      result.current.send('привет')
    })
    expect(result.current.streaming).toBe(true)
    expect(result.current.messages.at(-1)).toEqual({
      role: 'user',
      content: 'привет',
    })

    act(() => {
      captured.onClose?.()
    })
    expect(result.current.streaming).toBe(false)
    expect(result.current.interrupted).toBe(true)
    expect(result.current.closed).toBe(true)
    expect(result.current.messages).toEqual([{ role: 'user', content: 'привет' }])
  })

  it('hydrates stored messages after reconnect without clearing the list first', async () => {
    const pending = deferred<MessageOut[]>()
    listSessionMessages
      .mockResolvedValueOnce([])
      .mockReturnValueOnce(pending.promise)

    const { result } = renderHook(() => usePlannerSession('s1'))

    await waitFor(() => {
      expect(listSessionMessages).toHaveBeenCalledTimes(1)
    })

    act(() => {
      result.current.send('привет')
      captured.onClose?.()
    })
    expect(result.current.interrupted).toBe(true)
    expect(result.current.messages).toEqual([{ role: 'user', content: 'привет' }])

    act(() => {
      result.current.reconnect()
    })
    expect(result.current.reconnecting).toBe(true)
    expect(result.current.interrupted).toBe(false)
    expect(result.current.closed).toBe(false)
    expect(result.current.messages).toEqual([{ role: 'user', content: 'привет' }])

    await act(async () => {
      pending.resolve([
        storedMessage('user', 'привет', 1),
        storedMessage('assistant', 'ответ из БД', 2),
      ])
      await pending.promise
    })
    expect(result.current.messages).toEqual([
      { role: 'user', content: 'привет' },
      { role: 'assistant', content: 'ответ из БД' },
    ])
  })

  it('clears interrupted and closed when the session changes', () => {
    const { result, rerender } = renderHook(
      ({ id }: { id: string | null }) => usePlannerSession(id),
      { initialProps: { id: 's1' } },
    )

    act(() => {
      result.current.send('привет')
      captured.onClose?.()
    })
    expect(result.current.interrupted).toBe(true)
    expect(result.current.closed).toBe(true)

    rerender({ id: 's2' })
    expect(result.current.interrupted).toBe(false)
    expect(result.current.closed).toBe(false)
    expect(result.current.streaming).toBe(false)
    expect(result.current.messages).toEqual([])
  })
})
