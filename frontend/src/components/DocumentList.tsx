import { useRef, useState } from 'react'
import { extractApiDetail, type DocumentOut } from '../api.ts'
import type { UseDocumentsResult } from '../hooks/useDocuments.ts'

interface DocumentListProps {
  docs: UseDocumentsResult
  currentDocId: string | null
  onSelect: (id: string) => void
  uploadDisabled?: boolean
}

export function DocumentList({
  docs,
  currentDocId,
  onSelect,
  uploadDisabled = false,
}: DocumentListProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const onFile = async (file: File | undefined) => {
    if (!file || uploadDisabled) return
    setUploading(true)
    setErr(null)
    try {
      await docs.upload(file)
    } catch (e) {
      setErr(extractApiDetail(e))
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const disabled = uploadDisabled || uploading

  return (
    <div className="flex flex-col gap-2">
      <label
        className={
          'rounded-md border border-dashed border-line-strong px-3 py-2 text-center text-xs focus-within:outline-none focus-within:ring-2 focus-within:ring-brand ' +
          (disabled
            ? 'cursor-not-allowed text-ink-faint opacity-60'
            : 'cursor-pointer text-ink-faint hover:border-line-brand')
        }
      >
        {uploading ? 'Загрузка…' : '+ Загрузить документ'}
        <input
          ref={inputRef}
          type="file"
          accept=".md,.docx,.pdf,.csv,.xlsx,.xls,.ods,.tsv"
          className="sr-only"
          disabled={disabled}
          onChange={(e) => void onFile(e.target.files?.[0])}
        />
      </label>
      {err && (
        <p role="alert" className="text-xs text-danger-ink break-words">
          {err}
        </p>
      )}
      {docs.error && <p className="text-xs text-danger-ink">{docs.error}</p>}
      <ul className="flex flex-col gap-1">
        {docs.documents.map((d: DocumentOut) => (
          <li key={d.id}>
            <button
              type="button"
              className={
                'w-full truncate rounded px-2 py-1.5 text-left text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand ' +
                (d.id === currentDocId
                  ? 'bg-[var(--sidebar-selected)] text-[var(--sidebar-selected-ink)]'
                  : 'bg-surface-muted text-ink-muted hover:bg-surface-hover')
              }
              title={d.title}
              onClick={() => onSelect(d.id)}
            >
              <span className="badge-neutral mr-1">{d.kind}</span>
              {d.title}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
