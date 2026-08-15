import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getSessionArtifacts,
  getSessionDocuments,
  listSessionMessages,
  patchArtifact,
  patchSkillMeta,
  removeSessionDocument,
  type DocumentOut,
  type MessageOut,
  type SessionArtifact,
  type SkillMetaPatch,
} from '../api.ts'
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
  cancelling: boolean
  closed: boolean
  reconnecting: boolean
  error: string | null
  suggestions: string[]
  sessionDocuments: DocumentOut[]
  artifacts: SessionArtifact[]
  artifactsLoading: boolean
  artifactsError: string | null
  savePrompt: (content: string) => Promise<SessionArtifact>
  saveScript: (content: string) => Promise<SessionArtifact>
  saveMeta: (meta: SkillMetaPatch) => Promise<SessionArtifact>
  send: (text: string, docIds?: string[], docs?: DocumentOut[]) => void
  cancel: () => void
  reconnect: () => void
  removeDocument: (docId: string) => Promise<void>
  refreshSessionDocuments: () => Promise<void>
}

export interface UsePlannerSessionOptions {
  onSessionInvalid?: () => void
}

interface PendingSend {
  text: string
  docIds?: string[]
}

function mapStoredMessages(raw: MessageOut[]): PlannerMessage[] {
  const out: PlannerMessage[] = []
  for (const m of raw) {
    if (m.role === 'user' || m.role === 'assistant') {
      if (m.content === null) continue
      out.push({ role: m.role, content: m.content })
      continue
    }
    if (m.role === 'tool') {
      const toolName = m.tool_name ?? undefined
      let content: string
      if (m.content) {
        try {
          const parsed = JSON.parse(m.content) as { ok?: boolean }
          content = `← ${toolName ?? 'tool'}: ${parsed.ok ? 'ok' : 'fail'}`
        } catch {
          content = m.content
        }
      } else {
        content = `← ${toolName ?? 'tool'}: fail`
      }
      out.push({ role: 'tool', toolName, content })
    }
  }
  return out
}

function upsertArtifact(
  list: SessionArtifact[],
  next: SessionArtifact,
): SessionArtifact[] {
  const idx = list.findIndex((a) => a.type === next.type)
  if (idx === -1) return [...list, next]
  const copy = list.slice()
  copy[idx] = next
  return copy
}

export function usePlannerSession(
  sessionId: string | null,
  options?: UsePlannerSessionOptions,
): UsePlannerSessionResult {
  const [messages, setMessages] = useState<PlannerMessage[]>([])
  const [streaming, setStreaming] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [closed, setClosed] = useState(false)
  const [reconnecting, setReconnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [sessionDocuments, setSessionDocuments] = useState<DocumentOut[]>([])
  const [artifacts, setArtifacts] = useState<SessionArtifact[]>([])
  const [artifactsLoading, setArtifactsLoading] = useState(false)
  const [artifactsError, setArtifactsError] = useState<string | null>(null)
  const [reconnectNonce, setReconnectNonce] = useState(0)

  const connRef = useRef<PlannerConnection | null>(null)
  const assistantBufferRef = useRef<string>('')
  const pendingRef = useRef<PendingSend[]>([])
  const readyRef = useRef<boolean>(false)
  const streamingRef = useRef<boolean>(false)
  const skipHydrateRef = useRef<boolean>(false)
  const docsFromStreamRef = useRef<boolean>(false)
  const docsHydrateGenRef = useRef(0)
  const sessionIdRef = useRef<string | null>(sessionId)
  sessionIdRef.current = sessionId
  const prevSessionRef = useRef<string | null>(null)
  const hadErrorRef = useRef<boolean>(false)
  const onSessionInvalidRef = useRef(options?.onSessionInvalid)
  onSessionInvalidRef.current = options?.onSessionInvalid

  const resetLocal = useCallback(() => {
    setMessages([])
    setStreaming(false)
    setCancelling(false)
    setClosed(false)
    setReconnecting(false)
    setError(null)
    setSuggestions([])
    setSessionDocuments([])
    setArtifacts([])
    setArtifactsLoading(false)
    setArtifactsError(null)
    assistantBufferRef.current = ''
    pendingRef.current = []
    streamingRef.current = false
    skipHydrateRef.current = false
    docsFromStreamRef.current = false
    hadErrorRef.current = false
  }, [])

  const handleEvent = useCallback((e: ServerEvent) => {
    switch (e.type) {
      case 'token': {
        skipHydrateRef.current = true
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
        skipHydrateRef.current = true
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
        skipHydrateRef.current = true
        setMessages((prev) => [
          ...prev,
          {
            role: 'tool',
            toolName: e.name,
            content: `← ${e.name}: ${e.ok ? 'ok' : 'fail'}`,
          },
        ])
        break
      case 'finish': {
        assistantBufferRef.current = ''
        streamingRef.current = false
        setStreaming(false)
        setCancelling(false)
        docsFromStreamRef.current = true
        const sid = sessionIdRef.current
        if (sid) {
          const gen = ++docsHydrateGenRef.current
          void getSessionDocuments(sid).then(
            (docs) => {
              if (sessionIdRef.current !== sid) return
              if (docsHydrateGenRef.current !== gen) return
              setSessionDocuments(docs)
            },
            () => {},
          )
        }
        break
      }
      case 'suggestions':
        setSuggestions(e.items)
        break
      case 'session_docs':
        docsFromStreamRef.current = true
        docsHydrateGenRef.current += 1
        setSessionDocuments(e.documents)
        break
      case 'session_artifacts':
        setArtifacts(e.artifacts)
        setArtifactsError(null)
        break
      case 'error':
        hadErrorRef.current = true
        streamingRef.current = false
        setStreaming(false)
        setCancelling(false)
        if (/session not found/i.test(e.message)) {
          onSessionInvalidRef.current?.()
          break
        }
        setError(e.message)
        break
      case 'step':
      case 'verify':
        break
      default:
        break
    }
  }, [])

  useEffect(() => {
    if (!sessionId) {
      resetLocal()
      prevSessionRef.current = null
      return
    }

    if (prevSessionRef.current !== null && prevSessionRef.current !== sessionId) {
      resetLocal()
    }
    prevSessionRef.current = sessionId
    setClosed(false)
    readyRef.current = false
    skipHydrateRef.current =
      streamingRef.current ||
      assistantBufferRef.current.length > 0 ||
      pendingRef.current.length > 0
    const hydrateGen = ++docsHydrateGenRef.current

    let cancelled = false
    let intentionalClose = false

    void listSessionMessages(sessionId).then(
      (raw) => {
        if (cancelled || skipHydrateRef.current) return
        if (
          streamingRef.current ||
          assistantBufferRef.current.length > 0 ||
          pendingRef.current.length > 0
        ) {
          return
        }
        setMessages(mapStoredMessages(raw))
      },
      (e: unknown) => {
        if (cancelled) return
        const msg = e instanceof Error ? e.message : String(e)
        if (msg.startsWith('404')) {
          onSessionInvalidRef.current?.()
          return
        }
        setError(msg)
      },
    )

    void getSessionDocuments(sessionId).then(
      (docs) => {
        if (cancelled) return
        if (hydrateGen !== docsHydrateGenRef.current) return
        if (docsFromStreamRef.current) return
        if (
          skipHydrateRef.current ||
          streamingRef.current ||
          assistantBufferRef.current.length > 0 ||
          pendingRef.current.length > 0
        ) {
          return
        }
        setSessionDocuments(docs)
      },
      () => {},
    )

    setArtifactsLoading(true)
    setArtifactsError(null)
    void getSessionArtifacts(sessionId).then(
      (arts) => {
        if (cancelled) return
        setArtifacts(arts)
        setArtifactsLoading(false)
      },
      (e: unknown) => {
        if (cancelled) return
        setArtifacts([])
        setArtifactsLoading(false)
        setArtifactsError(e instanceof Error ? e.message : String(e))
      },
    )

    const conn = connectPlanner(sessionId, handleEvent, {
      onOpen: () => {
        readyRef.current = true
        setClosed(false)
        setReconnecting(false)
        const queued = pendingRef.current
        pendingRef.current = []
        for (const item of queued) {
          connRef.current?.send(item.text, item.docIds)
        }
      },
      onClose: () => {
        readyRef.current = false
        if (intentionalClose) return
        setReconnecting(false)
        if (!hadErrorRef.current) setClosed(true)
      },
    })
    connRef.current = conn
    return () => {
      intentionalClose = true
      cancelled = true
      conn.close()
      connRef.current = null
      readyRef.current = false
    }
  }, [sessionId, handleEvent, resetLocal, reconnectNonce])

  const send = useCallback((text: string, docIds?: string[], docs?: DocumentOut[]) => {
    const trimmed = text.trim()
    const ids = docIds && docIds.length > 0 ? docIds : undefined
    if (!trimmed && !ids) return
    skipHydrateRef.current = true
    setMessages((prev) => [...prev, { role: 'user', content: trimmed }])
    if (docs && docs.length > 0) {
      setSessionDocuments((prev) => {
        const seen = new Set(prev.map((d) => d.id))
        const next = prev.slice()
        for (const doc of docs) {
          if (seen.has(doc.id)) continue
          seen.add(doc.id)
          next.push(doc)
        }
        return next
      })
    }
    streamingRef.current = true
    setStreaming(true)
    setSuggestions([])
    assistantBufferRef.current = ''
    setError(null)
    if (readyRef.current && connRef.current) {
      connRef.current.send(trimmed, ids)
    } else {
      pendingRef.current.push({ text: trimmed, docIds: ids })
    }
  }, [])

  const cancel = useCallback(() => {
    connRef.current?.cancel()
    setCancelling(true)
  }, [])

  const reconnect = useCallback(() => {
    if (!sessionId) return
    setReconnecting(true)
    setClosed(false)
    setError(null)
    hadErrorRef.current = false
    setReconnectNonce((n) => n + 1)
  }, [sessionId])

  const removeDocument = useCallback(
    async (docId: string) => {
      if (!sessionId) return
      docsHydrateGenRef.current += 1
      docsFromStreamRef.current = true
      setSessionDocuments((prev) => prev.filter((d) => d.id !== docId))
      setError(null)
      try {
        await removeSessionDocument(sessionId, docId)
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e)
        if (msg.includes('session not found')) {
          onSessionInvalidRef.current?.()
          return
        }
        const docs = await getSessionDocuments(sessionId).catch(() => null)
        if (docs) setSessionDocuments(docs)
        setError(msg)
      }
    },
    [sessionId],
  )

  const refreshSessionDocuments = useCallback(async () => {
    if (!sessionId) return
    const gen = docsHydrateGenRef.current
    try {
      const docs = await getSessionDocuments(sessionId)
      if (sessionIdRef.current !== sessionId) return
      if (docsHydrateGenRef.current !== gen) return
      setSessionDocuments(docs)
    } catch {
      return
    }
  }, [sessionId])

  const savePrompt = useCallback(
    async (content: string) => {
      if (!sessionId) throw new Error('no session')
      const art = await patchArtifact(sessionId, 'prompt', content)
      setArtifacts((prev) => upsertArtifact(prev, art))
      return art
    },
    [sessionId],
  )

  const saveScript = useCallback(
    async (content: string) => {
      if (!sessionId) throw new Error('no session')
      const art = await patchArtifact(sessionId, 'script', content)
      setArtifacts((prev) => upsertArtifact(prev, art))
      return art
    },
    [sessionId],
  )

  const saveMeta = useCallback(
    async (meta: SkillMetaPatch) => {
      if (!sessionId) throw new Error('no session')
      const art = await patchSkillMeta(sessionId, meta)
      setArtifacts((prev) => upsertArtifact(prev, art))
      return art
    },
    [sessionId],
  )

  return {
    messages,
    streaming,
    cancelling,
    closed,
    reconnecting,
    error,
    suggestions,
    sessionDocuments,
    artifacts,
    artifactsLoading,
    artifactsError,
    savePrompt,
    saveScript,
    saveMeta,
    send,
    cancel,
    reconnect,
    removeDocument,
    refreshSessionDocuments,
  }
}
