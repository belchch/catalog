import type { PlannerMessage } from '../hooks/usePlannerSession.ts'

export function ChatMessage({ message }: { message: PlannerMessage }) {
  if (message.role === 'user') {
    return (
      <div className="my-2 flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-lg bg-indigo-600 px-3 py-2 text-sm text-white">
          {message.content}
        </div>
      </div>
    )
  }
  if (message.role === 'tool') {
    return (
      <div className="my-1 text-xs text-slate-400">
        <span className="font-mono">ℹ {message.content}</span>
      </div>
    )
  }
  return (
    <div className="my-2 flex justify-start">
      <div className="max-w-[80%] whitespace-pre-wrap rounded-lg bg-slate-800 px-3 py-2 text-sm text-slate-100">
        {message.content}
      </div>
    </div>
  )
}
