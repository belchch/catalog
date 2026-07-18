import { useRef, useState } from 'react'
import type { DocumentOut } from '../api.ts'
import type { UseDocumentsResult } from '../hooks/useDocuments.ts'

interface DocumentListProps {
  docs: UseDocumentsResult
  currentDocId: string | null
  onSelect: (id: string) => void
}

export function DocumentList({ docs, currentDocId, onSelect }: DocumentListProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const onFile = async (file: File | undefined) => {
    if (!file) return
    setUploading(true)
    setErr(null)
    try {
      await docs.upload(file)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <label className="cursor-pointer rounded-md border border-dashed border-slate-700 px-3 py-2 text-center text-xs text-slate-400 hover:border-slate-500">
        {uploading ? 'Загрузка…' : '+ Загрузить .md / .docx'}
        <input
          ref={inputRef}
          type="file"
          accept=".md,.docx"
          className="hidden"
          onChange={(e) => void onFile(e.target.files?.[0])}
        />
      </label>
      {err && <p className="text-xs text-red-400">{err}</p>}
      {docs.error && <p className="text-xs text-red-400">{docs.error}</p>}
      <ul className="flex flex-col gap-1">
        {docs.documents.map((d: DocumentOut) => (
          <li key={d.id}>
            <button
              className={
                'w-full truncate rounded px-2 py-1.5 text-left text-xs ' +
                (d.id === currentDocId
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-800/60 text-slate-300 hover:bg-slate-800')
              }
              title={d.title}
              onClick={() => onSelect(d.id)}
            >
              <span className="mr-1 rounded bg-slate-700/60 px-1 text-[10px] uppercase">
                {d.kind}
              </span>
              {d.title}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
