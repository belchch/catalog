import { useEffect, useRef, useState } from 'react'
import type { PlannerMessage } from '../hooks/usePlannerSession.ts'
import { ChatMessage } from './ChatMessage.tsx'

interface ChatProps {
  messages: PlannerMessage[]
  streaming: boolean
  closed: boolean
  error: string | null
  onSend: (text: string) => void
  onCreateSkill: () => void
  buildingSkill: boolean
}

export function Chat({
  messages,
  streaming,
  closed,
  error,
  onSend,
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

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {messages.length === 0 && (
          <p className="mt-8 text-center text-sm text-slate-500">
            Опишите задачу для документа — планировщик изучит документы и предложит скилл.
          </p>
        )}
        {messages.map((m, i) => (
          <ChatMessage key={i} message={m} />
        ))}
        {streaming && (
          <div className="my-2 text-xs text-slate-400">●●● планировщик думает…</div>
        )}
        {closed && <div className="my-2 text-xs text-amber-400">Соединение закрыто</div>}
        {error && <div className="my-2 text-xs text-red-400">Ошибка: {error}</div>}
        <div ref={bottomRef} />
      </div>
      <div className="border-t border-slate-800 p-3">
        <div className="flex gap-2">
          <input
            className="flex-1 rounded-md bg-slate-800 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-500"
            placeholder="Сообщение планировщику…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submit()
            }}
          />
          <button
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            onClick={submit}
            disabled={streaming}
          >
            Отправить
          </button>
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
