import { useCallback, useEffect, useRef, useState } from 'react'
import {
  connectPlanner,
  formatToolArgs,
  type PlannerConnection,
  type ServerEvent,
} from '../ws.ts'

export interface PlannerMessage {
  role: 'user' | 'assistant' | 'tool'
  content: string
  toolName?: string
}

export interface UsePlannerSessionResult {
  messages: PlannerMessage[]
  streaming: boolean
  closed: boolean
  error: string | null
  send: (text: string) => void
}

/**
 * Drives the planner WebSocket for a session.
 *
 * Outgoing messages are buffered until the socket is open, so `send` can be
 * called immediately after the session id is set (the connect effect runs on
 * the next render and flushes the buffer on open).
 */
export function usePlannerSession(sessionId: string | null): UsePlannerSessionResult {
  const [messages, setMessages] = useState<PlannerMessage[]>([])
  const [streaming, setStreaming] = useState(false)
  const [closed, setClosed] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const connRef = useRef<PlannerConnection | null>(null)
  const assistantBufferRef = useRef<string>('')
  const pendingRef = useRef<string[]>([])
  const readyRef = useRef<boolean>(false)

  const handleEvent = useCallback((e: ServerEvent) => {
    switch (e.type) {
      case 'token': {
        assistantBufferRef.current += e.delta
        const text = assistantBufferRef.current
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last && last.role === 'assistant') {
            return [...prev.slice(0, -1), { ...last, content: text }]
          }
          return [...prev, { role: 'assistant', content: text }]
        })
        break
      }
      case 'tool_call':
        setMessages((prev) => [
          ...prev,
          {
            role: 'tool',
            toolName: e.name,
            content: `→ ${e.name}(${formatToolArgs(e.arguments)})`,
          },
        ])
        break
      case 'tool_result':
        setMessages((prev) => [
          ...prev,
          {
            role: 'tool',
            toolName: e.name,
            content: `← ${e.name}: ${e.ok ? 'ok' : 'fail'}`,
          },
        ])
        break
      case 'finish':
        assistantBufferRef.current = ''
        setStreaming(false)
        break
      case 'error':
        setError(e.message)
        setStreaming(false)
        break
      case 'step':
      case 'verify':
        break
      default:
        break
    }
  }, [])

  useEffect(() => {
    if (!sessionId) return
    setMessages([])
    setStreaming(false)
    setClosed(false)
    setError(null)
    assistantBufferRef.current = ''
    pendingRef.current = []
    readyRef.current = false

    const conn = connectPlanner(sessionId, handleEvent, {
      onOpen: () => {
        readyRef.current = true
        const queued = pendingRef.current
        pendingRef.current = []
        for (const text of queued) connRef.current?.send(text)
      },
      onClose: () => {
        readyRef.current = false
        setClosed(true)
      },
    })
    connRef.current = conn
    return () => {
      conn.close()
      connRef.current = null
      readyRef.current = false
    }
  }, [sessionId, handleEvent])

  const send = useCallback((text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return
    setMessages((prev) => [...prev, { role: 'user', content: trimmed }])
    setStreaming(true)
    assistantBufferRef.current = ''
    setError(null)
    if (readyRef.current && connRef.current) {
      connRef.current.send(trimmed)
    } else {
      pendingRef.current.push(trimmed)
    }
  }, [])

  return { messages, streaming, closed, error, send }
}
