import { useState } from 'react'
import { ApiError } from '../api.ts'
import type { UseKbResult } from '../hooks/useKb.ts'

interface KBPanelProps {
  kb: UseKbResult
}

/** ADR-0022: connect a KB-repo, show pending changes, commit them. */
export function KBPanel({ kb }: KBPanelProps) {
  const [path, setPath] = useState('')
  const [remote, setRemote] = useState('')
  const [pushEnabled, setPushEnabled] = useState(false)
  const [message, setMessage] = useState('')
  const [connecting, setConnecting] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [commitResult, setCommitResult] = useState<string | null>(null)
  // Set when the backend refuses a connect that would reconcile the whole
  // index away (409): the target holds no documents, or has vanished. Holding
  // the message here turns it into an explicit confirm instead of a dead end.
  const [needsForce, setNeedsForce] = useState<string | null>(null)

  const onConnect = async (force = false) => {
    if (!path.trim()) return
    setConnecting(true)
    setCommitResult(null)
    setNeedsForce(null)
    try {
      await kb.connect({
        path: path.trim(),
        remote: remote.trim() || undefined,
        push_enabled: pushEnabled,
        force: force || undefined,
      })
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setNeedsForce(e.detail)
      // otherwise surfaced via kb.error
    } finally {
      setConnecting(false)
    }
  }

  const onCommit = async () => {
    if (!message.trim()) return
    setCommitting(true)
    setCommitResult(null)
    try {
      const result = await kb.commit(message.trim())
      setCommitResult(
        result.sha
          ? `Коммит ${result.sha}${result.push_warning ? ` (push: ${result.push_warning})` : ''}`
          : 'Нечего коммитить',
      )
      setMessage('')
    } catch {
      // surfaced via kb.error
    } finally {
      setCommitting(false)
    }
  }

  const pendingCount = kb.status
    ? kb.status.staged_add.length +
      kb.status.staged_delete.length +
      kb.status.staged_modify.length +
      kb.status.unstaged.length +
      kb.status.untracked.length
    : 0

  return (
    <div className="flex flex-col gap-3 text-xs">
      <div className="flex flex-col gap-1.5">
        <input
          className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-200"
          placeholder="Путь к репозиторию базы знаний"
          value={path}
          onChange={(e) => setPath(e.target.value)}
        />
        <input
          className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-200"
          placeholder="Remote URL (опционально)"
          value={remote}
          onChange={(e) => setRemote(e.target.value)}
        />
        <label className="flex items-center gap-1.5 text-slate-400">
          <input
            type="checkbox"
            checked={pushEnabled}
            onChange={(e) => setPushEnabled(e.target.checked)}
          />
          Push при коммите
        </label>
        <button
          type="button"
          className="rounded bg-indigo-600 px-2 py-1 text-white disabled:opacity-50"
          onClick={() => void onConnect()}
          disabled={connecting || !path.trim()}
        >
          {connecting ? 'Подключение…' : 'Подключить'}
        </button>
      </div>

      {needsForce && (
        <div className="flex flex-col gap-1.5 rounded border border-amber-700/60 bg-amber-950/30 p-2">
          <p className="text-amber-300">{needsForce}</p>
          <button
            type="button"
            className="self-start rounded bg-amber-700 px-2 py-1 text-white disabled:opacity-50"
            onClick={() => void onConnect(true)}
            disabled={connecting}
          >
            Подключить всё равно
          </button>
        </div>
      )}

      {kb.status && (
        <div className="flex flex-col gap-1 rounded border border-slate-800 bg-slate-900/60 p-2">
          <div className="truncate text-slate-400" title={kb.status.repo_root}>
            {kb.status.repo_root}
          </div>
          <div className="text-slate-300">
            {kb.status.document_count} документ(ов), {kb.status.skill_count} скилл(ов)
          </div>
          <div className={kb.status.is_clean ? 'text-slate-500' : 'text-amber-400'}>
            {kb.status.is_clean
              ? 'Нет незакоммиченных изменений'
              : `Незакоммиченных изменений: ${pendingCount}`}
          </div>
          <button
            type="button"
            className="self-start rounded bg-slate-800 px-2 py-1 text-slate-300 hover:bg-slate-700 disabled:opacity-50"
            onClick={() => void kb.rescan()}
            disabled={kb.loading}
          >
            Rescan
          </button>
        </div>
      )}

      {kb.status && !kb.status.is_clean && (
        <div className="flex flex-col gap-1.5">
          <input
            className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-200"
            placeholder="Сообщение коммита"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
          <button
            type="button"
            className="self-start rounded bg-emerald-600 px-2 py-1 text-white disabled:opacity-50"
            onClick={() => void onCommit()}
            disabled={committing || !message.trim()}
          >
            {committing ? 'Коммит…' : 'Commit'}
          </button>
        </div>
      )}

      {commitResult && <p className="text-slate-400">{commitResult}</p>}
      {/* A captured 409 is already rendered above as an actionable confirm —
          don't repeat it here as a raw "409 Conflict: {...}" dump. */}
      {kb.error && !needsForce && <p className="text-red-400">{kb.error}</p>}
    </div>
  )
}
