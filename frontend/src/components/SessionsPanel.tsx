import { useState } from 'react'
import type { SessionOut } from '../api.ts'
import type { UseSessionsResult } from '../hooks/useSessions.ts'

interface SessionsPanelProps {
  sessions: UseSessionsResult
  currentSessionId: string | null
  onSelect: (id: string) => void
  onDelete: (id: string) => void
}

export function SessionsPanel({
  sessions,
  currentSessionId,
  onSelect,
  onDelete,
}: SessionsPanelProps) {
  const [confirmId, setConfirmId] = useState<string | null>(null)

  const clearConfirm = () => setConfirmId(null)

  return (
    <div className="flex flex-col gap-2">
      {sessions.error && <p className="text-xs text-red-400">{sessions.error}</p>}
      {sessions.sessions.length === 0 && sessions.loading && (
        <p className="text-xs text-slate-500">Загрузка…</p>
      )}
      {!sessions.loading && sessions.sessions.length === 0 && !sessions.error && (
        <p className="text-xs text-slate-500">Пока нет сохранённых сессий</p>
      )}
      <ul className="flex flex-col gap-1">
        {sessions.sessions.map((s: SessionOut) => {
          const active = s.id === currentSessionId
          const title = s.title ?? 'Без названия'
          const confirming = confirmId === s.id
          return (
            <li key={s.id} className="flex items-stretch gap-1">
              <button
                type="button"
                className={
                  'min-w-0 flex-1 rounded px-2 py-1.5 text-left text-xs ' +
                  (active
                    ? 'bg-indigo-600 text-white'
                    : 'bg-slate-800/60 text-slate-300 hover:bg-slate-800')
                }
                title={title}
                aria-current={active ? 'true' : undefined}
                onClick={() => {
                  clearConfirm()
                  onSelect(s.id)
                }}
                onBlur={(e) => {
                  if (!e.currentTarget.parentElement?.contains(e.relatedTarget as Node)) {
                    clearConfirm()
                  }
                }}
              >
                <span className="block truncate">{title}</span>
                <span
                  className={
                    'mt-0.5 flex items-center gap-1 text-[10px] ' +
                    (active ? 'text-indigo-100/80' : 'text-slate-400')
                  }
                >
                  <span>{new Date(s.updated_at).toLocaleString()}</span>
                  <span className="rounded bg-slate-700/60 px-1 text-[10px] uppercase">
                    {s.status}
                  </span>
                </span>
              </button>
              <div className="flex shrink-0 flex-col justify-center gap-0.5">
                {confirming ? (
                  <>
                    <button
                      type="button"
                      className="rounded px-1.5 py-0.5 text-[10px] text-red-400 hover:bg-slate-800"
                      onClick={(e) => {
                        e.stopPropagation()
                        setConfirmId(null)
                        onDelete(s.id)
                      }}
                    >
                      Удалить
                    </button>
                    <button
                      type="button"
                      className="rounded px-1.5 py-0.5 text-[10px] text-slate-400 hover:bg-slate-800"
                      onClick={(e) => {
                        e.stopPropagation()
                        clearConfirm()
                      }}
                    >
                      Отмена
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="rounded px-1.5 py-1 text-xs text-slate-400 hover:text-red-400"
                    aria-label="Удалить сессию"
                    onClick={(e) => {
                      e.stopPropagation()
                      setConfirmId(s.id)
                    }}
                  >
                    ×
                  </button>
                )}
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
