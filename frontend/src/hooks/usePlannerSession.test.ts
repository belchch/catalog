import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { DocumentOut } from '../api.ts'
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
  send: ReturnType<typeof vi.fn>
  close: ReturnType<typeof vi.fn>
  cancel: ReturnType<typeof vi.fn>
}

const captured: CapturedConn = {
  onEvent: null,
  onOpen: undefined,
  send: vi.fn(),
  close: vi.fn(),
  cancel: vi.fn(),
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
    captured.send = vi.fn()
    captured.close = vi.fn()
    captured.cancel = vi.fn()
    connectPlanner.mockImplementation(
      (
        _sessionId: string,
        onEvent: (e: ServerEvent) => void,
        opts?: { onOpen?: () => void },
      ): PlannerConnection => {
        captured.onEvent = onEvent
        captured.onOpen = opts?.onOpen
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
})
