import { useCallback, useEffect, useState } from 'react'
import type { FsEntry, ScanReport, WorkspaceOpenResult, WorkspaceOut } from '../api.ts'
import {
  ApiError,
  browseFs,
  extractApiDetail,
  getCurrentWorkspace,
  listWorkspaces,
  openWorkspace,
  rescanWorkspace,
} from '../api.ts'

export interface UseWorkspaceResult {
  current: WorkspaceOut | null
  recents: WorkspaceOut[]
  loading: boolean
  error: string | null
  busy: boolean
  refreshCurrent: () => Promise<WorkspaceOut | null>
  refreshRecents: () => Promise<void>
  open: (path: string, confirm?: boolean) => Promise<WorkspaceOpenResult>
  rescan: () => Promise<ScanReport>
  browse: (path?: string) => Promise<FsEntry[]>
  clearError: () => void
}

export function useWorkspace(): UseWorkspaceResult {
  const [current, setCurrent] = useState<WorkspaceOut | null>(null)
  const [recents, setRecents] = useState<WorkspaceOut[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refreshCurrent = useCallback(async () => {
    try {
      const ws = await getCurrentWorkspace()
      setCurrent(ws)
      return ws
    } catch (e) {
      setError(extractApiDetail(e))
      throw e
    }
  }, [])

  const refreshRecents = useCallback(async () => {
    try {
      setRecents(await listWorkspaces())
    } catch (e) {
      setError(extractApiDetail(e))
      throw e
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void Promise.all([getCurrentWorkspace(), listWorkspaces()])
      .then(([ws, list]) => {
        if (cancelled) return
        setCurrent(ws)
        setRecents(list)
        setError(null)
      })
      .catch((e) => {
        if (!cancelled) setError(extractApiDetail(e))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const open = useCallback(async (path: string, confirm = false) => {
    setBusy(true)
    setError(null)
    try {
      const result = await openWorkspace(path, confirm)
      if (result.status === 'ok') {
        const ws: WorkspaceOut = {
          path: result.path ?? path,
          display_name: result.display_name,
          last_opened: new Date().toISOString(),
        }
        setCurrent(ws)
        try {
          setRecents(await listWorkspaces())
        } catch {}
      }
      return result
    } catch (e) {
      const detail = extractApiDetail(e)
      if (!(e instanceof ApiError && e.status === 409)) {
        setError(detail)
      }
      throw e
    } finally {
      setBusy(false)
    }
  }, [])

  const rescan = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      return await rescanWorkspace()
    } catch (e) {
      setError(extractApiDetail(e))
      throw e
    } finally {
      setBusy(false)
    }
  }, [])

  const browse = useCallback(async (path?: string) => {
    return browseFs(path)
  }, [])

  const clearError = useCallback(() => setError(null), [])

  return {
    current,
    recents,
    loading,
    error,
    busy,
    refreshCurrent,
    refreshRecents,
    open,
    rescan,
    browse,
    clearError,
  }
}
