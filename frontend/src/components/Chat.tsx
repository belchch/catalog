import { useEffect, useRef, useState } from 'react'
import type { PlannerMessage } from '../hooks/usePlannerSession.ts'
import { ChatMessage } from './ChatMessage.tsx'

// Static starter quick-replies for an empty chat (CATALOG-13). Mirrors the
// backend STARTER_SUGGESTIONS; shown before a session is connected and for a
// freshly opened empty session.
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
  error: string | null
  suggestions: string[]
  onSend: (text: string) => void
  onCancel: () => void
  onCreateSkill: () => void
  buildingSkill: boolean
}

export function Chat({
  messages,
  streaming,
  cancelling,
  closed,
  error,
  suggestions,
  onSend,
  onCancel,
  onCreateSkill,
  buildingSkill,
}: ChatProps) {
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const submit = () => {
    const text = input.trim()
    if (!text || streaming) return
    onSend(text)
    setInput('')
  }

  // CATALOG-13: quick-reply chips. Hidden while streaming; the starter set is
  // shown for an empty chat, otherwise the model-suggested items are used.
  const visibleSuggestions = streaming
    ? []
    : messages.length === 0
      ? STARTER_SUGGESTIONS
      : suggestions

  return (
    <div className="flex h-full flex-col">
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
        {closed && <div className="my-2 text-xs text-amber-400">Соединение закрыто</div>}
        {error && <div className="my-2 text-xs text-red-400">Ошибка: {error}</div>}
        <div ref={bottomRef} />
      </div>
      <div className="border-t border-slate-800 p-3">
        {visibleSuggestions.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
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
        <div className="flex gap-2">
          <input
            className="flex-1 rounded-md bg-slate-800 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-500 disabled:opacity-50"
            placeholder="Сообщение планировщику…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submit()
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
              disabled={streaming}
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
          {buildingSkill ? 'Собираю скилл…' : 'Создать скилл из сессии'}
        </button>
      </div>
    </div>
  )
}
