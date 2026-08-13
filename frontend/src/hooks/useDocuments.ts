import { useCallback, useEffect, useState } from 'react'
import type { DocumentOut } from '../api.ts'
import { listDocuments, uploadDocument } from '../api.ts'

export interface UseDocumentsResult {
  documents: DocumentOut[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  upload: (file: File) => Promise<DocumentOut>
}

export function useDocuments(enabled = true): UseDocumentsResult {
  const [documents, setDocuments] = useState<DocumentOut[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!enabled) {
      setDocuments([])
      setError(null)
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      setDocuments(await listDocuments())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [enabled])

  const upload = useCallback(async (file: File) => {
    const doc = await uploadDocument(file)
    setDocuments((prev) => [doc, ...prev])
    return doc
  }, [])

  useEffect(() => {
    if (!enabled) {
      setDocuments([])
      setError(null)
      setLoading(false)
      return
    }
    void refresh()
  }, [refresh, enabled])

  return { documents, loading, error, refresh, upload }
}
