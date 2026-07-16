import { useState } from 'react'
import type { DocumentOut } from '../api.ts'
import type { UseSkillsResult } from '../hooks/useSkills.ts'

interface SkillsPanelProps {
  skills: UseSkillsResult
  documents: DocumentOut[]
  defaultDocId: string | null
  onApply: (skillId: string, docId: string) => void
}

export function SkillsPanel({ skills, documents, defaultDocId, onApply }: SkillsPanelProps) {
  const [target, setTarget] = useState<Record<string, string>>({})

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
          const docId = target[s.id] ?? defaultDocId ?? documents[0]?.id ?? ''
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
                          ? 'bg-amber-600/30 text-amber-300'
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
                  <>
                    <select
                      className="max-w-[140px] rounded bg-slate-800 px-1.5 py-1 text-[11px] text-slate-200"
                      value={docId}
                      onChange={(e) =>
                        setTarget((p) => ({ ...p, [s.id]: e.target.value }))
                      }
                    >
                      {documents.length === 0 && <option value="">нет документов</option>}
                      {documents.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.title}
                        </option>
                      ))}
                    </select>
                    <button
                      className="rounded bg-indigo-600 px-2 py-1 text-[11px] text-white disabled:opacity-50"
                      disabled={!docId}
                      onClick={() => docId && onApply(s.id, docId)}
                    >
                      Применить
                    </button>
                  </>
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
