import { useCallback, useEffect, useState } from 'react'
import type {
  FsEntry,
  ScanReport,
  WorkspaceBusyReason,
  WorkspaceOpenResult,
  WorkspaceOut,
} from '../api.ts'
import {
  ApiError,
  browseFs,
  extractApiDetail,
  getCurrentWorkspace,
  getWorkspaceBusy,
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
  blocked: boolean
  blockedReason: WorkspaceBusyReason | null
  refreshCurrent: () => Promise<WorkspaceOut | null>
  refreshRecents: () => Promise<void>
  refreshBlocked: () => Promise<void>
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
  const [blocked, setBlocked] = useState(false)
  const [blockedReason, setBlockedReason] = useState<WorkspaceBusyReason | null>(
    null,
  )

  const refreshBlocked = useCallback(async () => {
    try {
      const status = await getWorkspaceBusy()
      setBlocked(status.busy)
      setBlockedReason(status.busy ? status.reason : null)
    } catch {
      setBlocked(false)
      setBlockedReason(null)
    }
  }, [])

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

  useEffect(() => {
    const onFocus = () => {
      void refreshBlocked()
    }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [refreshBlocked])

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
    blocked,
    blockedReason,
    refreshCurrent,
    refreshRecents,
    refreshBlocked,
    open,
    rescan,
    browse,
    clearError,
  }
}
