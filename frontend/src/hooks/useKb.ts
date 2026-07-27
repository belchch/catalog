import { useCallback, useEffect, useState } from 'react'
import type { KBStatusOut } from '../api.ts'
import { commitKB, connectKB, getKBStatus, rescanKB } from '../api.ts'

export interface UseKbResult {
  status: KBStatusOut | null
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  connect: (params: {
    path: string
    remote?: string
    push_enabled?: boolean
    force?: boolean
  }) => Promise<void>
  rescan: () => Promise<void>
  commit: (message: string) => Promise<{ sha: string | null; push_warning?: string | null }>
}

export function useKb(): UseKbResult {
  const [status, setStatus] = useState<KBStatusOut | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setStatus(await getKBStatus())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  const connect = useCallback(
    async (params: { path: string; remote?: string; push_enabled?: boolean; force?: boolean }) => {
      setLoading(true)
      setError(null)
      try {
        await connectKB(params)
        await refresh()
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
        throw e
      } finally {
        setLoading(false)
      }
    },
    [refresh],
  )

  const rescan = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      await rescanKB()
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [refresh])

  const commit = useCallback(
    async (message: string) => {
      setLoading(true)
      setError(null)
      try {
        const result = await commitKB(message)
        await refresh()
        return result
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
        throw e
      } finally {
        setLoading(false)
      }
    },
    [refresh],
  )

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { status, loading, error, refresh, connect, rescan, commit }
}
