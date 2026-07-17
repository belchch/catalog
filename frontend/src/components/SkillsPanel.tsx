import { useState } from 'react'
import type { DocumentOut } from '../api.ts'
import type { UseSkillsResult } from '../hooks/useSkills.ts'

interface SkillsPanelProps {
  skills: UseSkillsResult
  documents: DocumentOut[]
  defaultDocId: string | null
  onApply: (skillId: string, docIds: string[]) => void
}

export function SkillsPanel({ skills, documents, defaultDocId, onApply }: SkillsPanelProps) {
  // CATALOG-4: each skill keeps a *list* of selected input documents.
  const [target, setTarget] = useState<Record<string, string[]>>({})

  const selectedFor = (skillId: string): string[] => {
    const existing = target[skillId]
    if (existing) return existing
    // Default to the currently open document so the common single-doc case
    // still works without an extra click.
    return defaultDocId ? [defaultDocId] : []
  }

  const toggleDoc = (skillId: string, docId: string) => {
    setTarget((prev) => {
      const current = prev[skillId] ?? (defaultDocId ? [defaultDocId] : [])
      const next = current.includes(docId)
        ? current.filter((id) => id !== docId)
        : [...current, docId]
      return { ...prev, [skillId]: next }
    })
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-200">Скиллы</h2>
        <button
          className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300 disabled:opacity-50"
          onClick={() => void skills.refresh()}
          disabled={skills.loading}
        >
          {skills.loading ? '…' : 'Обновить'}
        </button>
      </div>
      {skills.error && <p className="text-xs text-red-400">{skills.error}</p>}
      <ul className="flex flex-col gap-2">
        {skills.skills.map((s) => {
          const selected = selectedFor(s.id)
          return (
            <li key={s.id} className="rounded-md border border-slate-800 bg-slate-900/60 p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-xs font-medium text-slate-200">{s.name}</span>
                <div className="flex items-center gap-1.5">
                  {s.tags.map((tag) => (
                    <span
                      key={tag}
                      className={
                        'rounded px-1.5 py-0.5 text-[10px] uppercase ' +
                        (tag === 'python'
                          ? 'bg-sky-600/30 text-sky-300'
                          : 'bg-fuchsia-600/30 text-fuchsia-300')
                      }
                    >
                      {tag}
                    </span>
                  ))}
                  <span
                    className={
                      'rounded px-1.5 py-0.5 text-[10px] uppercase ' +
                      (s.status === 'committed'
                        ? 'bg-emerald-600/30 text-emerald-300'
                        : 'bg-amber-600/30 text-amber-300')
                    }
                  >
                    {s.status}
                  </span>
                </div>
              </div>
              {s.description && (
                <p className="mt-1 text-[11px] text-slate-400">{s.description}</p>
              )}
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {s.status === 'draft' && (
                  <button
                    className="rounded bg-slate-700 px-2 py-1 text-[11px] text-slate-200"
                    onClick={() => void skills.commit(s.id)}
                  >
                    Коммит
                  </button>
                )}
                {s.status === 'committed' && (
                  <div className="flex w-full flex-col gap-1.5">
                    {documents.length === 0 && (
                      <span className="text-[11px] text-slate-500">нет документов</span>
                    )}
                    {documents.length > 0 && (
                      <ul className="flex max-h-32 flex-col gap-0.5 overflow-y-auto">
                        {documents.map((d) => {
                          const checked = selected.includes(d.id)
                          return (
                            <li key={d.id}>
                              <label className="flex items-center gap-1.5 text-[11px] text-slate-300">
                                <input
                                  type="checkbox"
                                  className="h-3 w-3 accent-indigo-500"
                                  checked={checked}
                                  onChange={() => toggleDoc(s.id, d.id)}
                                />
                                <span className="truncate">{d.title}</span>
                              </label>
                            </li>
                          )
                        })}
                      </ul>
                    )}
                    <button
                      className="rounded bg-indigo-600 px-2 py-1 text-[11px] text-white disabled:opacity-50"
                      disabled={selected.length === 0}
                      onClick={() => selected.length > 0 && onApply(s.id, selected)}
                    >
                      Применить{selected.length > 1 ? ` (${selected.length})` : ''}
                    </button>
                  </div>
                )}
              </div>
            </li>
          )
        })}
        {skills.skills.length === 0 && (
          <p className="text-xs text-slate-500">
            Скиллов пока нет — создайте из сессии планировщика.
          </p>
        )}
      </ul>
    </div>
  )
}
