import { useCallback, useEffect, useState } from 'react'
import type { SessionOut } from '../api.ts'
import { deleteSession, listSessions } from '../api.ts'

export interface UseSessionsResult {
  sessions: SessionOut[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  remove: (id: string) => Promise<void>
}

export function useSessions(): UseSessionsResult {
  const [sessions, setSessions] = useState<SessionOut[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setSessions(await listSessions())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  const remove = useCallback(async (id: string) => {
    await deleteSession(id)
    setSessions((prev) => prev.filter((s) => s.id !== id))
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { sessions, loading, error, refresh, remove }
}
