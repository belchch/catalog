import { useEffect, useRef, useState } from 'react'
import type { DocumentOut } from '../api.ts'
import type { PlannerMessage } from '../hooks/usePlannerSession.ts'
import { ChatMessage } from './ChatMessage.tsx'
import { DocumentCombobox } from './DocumentCombobox.tsx'

const STARTER_SUGGESTIONS = [
  'Изучи доступные документы',
  'Опиши задачу для скилла',
  'Какие документы уже есть?',
]

interface ChatProps {
  messages: PlannerMessage[]
  streaming: boolean
  cancelling: boolean
  closed: boolean
  reconnecting: boolean
  error: string | null
  suggestions: string[]
  documents: DocumentOut[]
  sessionDocuments: DocumentOut[]
  sessionId: string | null
  onSend: (text: string, docIds?: string[]) => void
  onCancel: () => void
  onReconnect: () => void
  onRemoveDocument?: (docId: string) => void
  onCreateSkill: () => void
  buildingSkill: boolean
  editingSkillName: string | null
}

export function Chat({
  messages,
  streaming,
  cancelling,
  closed,
  reconnecting,
  error,
  suggestions,
  documents,
  sessionDocuments,
  sessionId,
  onSend,
  onCancel,
  onReconnect,
  onRemoveDocument,
  onCreateSkill,
  buildingSkill,
  editingSkillName,
}: ChatProps) {
  const [input, setInput] = useState('')
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([])
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    setSelectedDocIds([])
  }, [sessionId])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [input])

  const submit = () => {
    const text = input.trim()
    if (streaming) return
    if (!text && selectedDocIds.length === 0) return
    onSend(text, selectedDocIds.length > 0 ? selectedDocIds : undefined)
    setInput('')
    setSelectedDocIds([])
  }

  const canSubmit = !streaming && (input.trim().length > 0 || selectedDocIds.length > 0)

  const visibleSuggestions = streaming
    ? []
    : messages.length === 0
      ? STARTER_SUGGESTIONS
      : suggestions

  const selectedDocs = selectedDocIds
    .map((id) => documents.find((d) => d.id === id))
    .filter((d): d is DocumentOut => d != null)

  const removeSelected = (id: string) => {
    if (streaming) return
    setSelectedDocIds((prev) => prev.filter((x) => x !== id))
  }

  return (
    <div className="flex h-full flex-col">
      {editingSkillName && (
        <div className="bg-indigo-900/40 px-4 py-1.5 text-xs text-indigo-200">
          Редактирование: {editingSkillName}
        </div>
      )}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {messages.length === 0 && (
          <p className="mt-8 text-center text-sm text-slate-500">
            Опишите задачу для документа — планировщик изучит документы и предложит скилл.
          </p>
        )}
        {messages.map((m, i) => (
          <ChatMessage
            key={i}
            message={m}
            onRepeat={onSend}
            streaming={streaming}
            closed={closed}
          />
        ))}
        {streaming && (
          <div className="my-2 text-xs text-slate-400">●●● планировщик думает…</div>
        )}
        {(closed || reconnecting) && (
          <div
            className="my-2 flex items-center gap-2 text-xs"
            role="status"
            aria-live="polite"
            aria-busy={reconnecting}
          >
            <span className="text-amber-400">
              {reconnecting ? 'Переподключаю…' : 'Соединение закрыто'}
            </span>
            <button
              type="button"
              className="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 transition-colors hover:border-indigo-500 hover:bg-slate-800 disabled:opacity-50"
              onClick={onReconnect}
              disabled={reconnecting}
              aria-busy={reconnecting}
            >
              {reconnecting ? 'Переподключаю…' : 'Переподключить'}
            </button>
          </div>
        )}
        {error && <div className="my-2 text-xs text-red-400">Ошибка: {error}</div>}
        <div ref={bottomRef} />
      </div>
      <div className="border-t border-slate-800 p-3">
        {sessionDocuments.length > 0 && (
          <section className="mb-2" aria-label="Документы в сессии">
            <h2 className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">
              Документы в сессии
            </h2>
            <p className="mb-1 text-[11px] text-slate-600">
              Агент видит только эти документы
            </p>
            <ul className="flex flex-wrap gap-1.5" role="list">
              {sessionDocuments.map((d) => (
                <li
                  key={d.id}
                  role="listitem"
                  className="inline-flex items-center gap-1 rounded-full border border-slate-700 bg-slate-800/60 px-2.5 py-1 text-xs text-slate-300"
                >
                  <span className="rounded bg-slate-700/60 px-1 text-[10px] uppercase text-slate-400">
                    {d.kind}
                  </span>
                  <span className="truncate">{d.title}</span>
                  <button
                    type="button"
                    className="ml-0.5 text-slate-400 hover:text-slate-100 disabled:opacity-50"
                    aria-label={`Убрать ${d.title} из сессии`}
                    disabled={streaming}
                    onClick={() => onRemoveDocument?.(d.id)}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          {selectedDocs.map((d) => (
            <span
              key={d.id}
              className="inline-flex items-center gap-1 rounded-full border border-indigo-500/40 bg-indigo-600/15 px-2.5 py-1 text-xs text-indigo-100"
            >
              <span className="rounded bg-slate-700/60 px-1 text-[10px] uppercase text-slate-400">
                {d.kind}
              </span>
              <span className="truncate">{d.title}</span>
              <button
                type="button"
                className="ml-0.5 text-slate-400 hover:text-slate-100 disabled:opacity-50"
                aria-label={`Убрать ${d.title}`}
                disabled={streaming}
                onClick={() => removeSelected(d.id)}
              >
                ×
              </button>
            </span>
          ))}
          <div className="w-44 max-w-[12rem]">
            <DocumentCombobox
              multiple
              documents={documents}
              values={selectedDocIds}
              onChange={setSelectedDocIds}
              ariaLabel="Добавить документы в сессию"
              placeholder="+ документ"
              disabled={streaming}
              placement="top"
              triggerClassName="flex w-full items-center justify-between rounded-full border border-slate-700 bg-slate-800/60 px-3 py-1 text-left text-xs text-slate-200 hover:border-indigo-500 hover:bg-slate-800 disabled:opacity-50"
            />
          </div>
        </div>
        {visibleSuggestions.length > 0 && (
          <div
            className="mb-2 flex flex-wrap gap-2"
            role="group"
            aria-label="Быстрые ответы"
          >
            {visibleSuggestions.map((s) => (
              <button
                key={s}
                className="rounded-full border border-slate-700 bg-slate-800/60 px-3 py-1 text-xs text-slate-200 transition-colors hover:border-indigo-500 hover:bg-slate-800 disabled:opacity-50"
                onClick={() => onSend(s)}
                disabled={streaming}
              >
                {s}
              </button>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            rows={1}
            className="max-h-40 flex-1 resize-none overflow-y-auto rounded-md bg-slate-800 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-500 disabled:opacity-50"
            placeholder="Сообщение планировщику…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key !== 'Enter') return
              if (e.shiftKey || e.ctrlKey || e.metaKey || e.altKey) return
              if (e.nativeEvent.isComposing || e.keyCode === 229) return
              e.preventDefault()
              submit()
            }}
            disabled={streaming}
          />
          {streaming ? (
            <button
              className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              onClick={onCancel}
              disabled={cancelling}
            >
              {cancelling ? 'Останавливаю…' : 'Стоп'}
            </button>
          ) : (
            <button
              className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              onClick={submit}
              disabled={!canSubmit}
            >
              Отправить
            </button>
          )}
        </div>
        <button
          className="mt-2 rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-300 disabled:opacity-50"
          onClick={onCreateSkill}
          disabled={buildingSkill || messages.length === 0}
        >
          {buildingSkill
            ? 'Собираю скилл…'
            : editingSkillName
              ? 'Сохранить изменения'
              : 'Создать скилл из сессии'}
        </button>
      </div>
    </div>
  )
}
