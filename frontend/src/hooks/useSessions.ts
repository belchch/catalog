import { useCallback, useEffect, useState } from 'react'
import type { SessionOut } from '../api.ts'
import { deleteSession, listSessions } from '../api.ts'

export interface UseSessionsResult {
  sessions: SessionOut[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  remove: (id: string) => Promise<void>
  patchLocal: (session: SessionOut) => void
}

export function useSessions(enabled = true): UseSessionsResult {
  const [sessions, setSessions] = useState<SessionOut[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!enabled) {
      setSessions([])
      setError(null)
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      setSessions(await listSessions())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [enabled])

  const remove = useCallback(async (id: string) => {
    await deleteSession(id)
    setSessions((prev) => prev.filter((s) => s.id !== id))
  }, [])

  const patchLocal = useCallback((session: SessionOut) => {
    setSessions((prev) => {
      const idx = prev.findIndex((s) => s.id === session.id)
      if (idx < 0) return [session, ...prev]
      const next = [...prev]
      next[idx] = session
      return next
    })
  }, [])

  useEffect(() => {
    if (!enabled) {
      setSessions([])
      setError(null)
      setLoading(false)
      return
    }
    void refresh()
  }, [refresh, enabled])

  return { sessions, loading, error, refresh, remove, patchLocal }
}
