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

export function useDocuments(): UseDocumentsResult {
  const [documents, setDocuments] = useState<DocumentOut[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setDocuments(await listDocuments())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  const upload = useCallback(async (file: File) => {
    const doc = await uploadDocument(file)
    setDocuments((prev) => [doc, ...prev])
    return doc
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { documents, loading, error, refresh, upload }
}
