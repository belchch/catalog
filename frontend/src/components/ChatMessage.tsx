import type { PlannerMessage } from '../hooks/usePlannerSession.ts'
import { MessageCommands } from './MessageCommands.tsx'

interface ChatMessageProps {
  message: PlannerMessage
  /** Re-send handler for the «Повторить» command under user messages. */
  onRepeat?: (content: string) => void
  /** True while a planner response is streaming — blocks «Повторить». */
  streaming?: boolean
  /** True when the socket is closed — also blocks «Повторить». */
  closed?: boolean
}

export function ChatMessage({ message, onRepeat, streaming, closed }: ChatMessageProps) {
  if (message.role === 'user') {
    return (
      <div className="my-2 flex flex-col items-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-lg bg-indigo-600 px-3 py-2 text-sm text-white">
          {message.content}
        </div>
        <MessageCommands
          content={message.content}
          onRepeat={onRepeat}
          streaming={streaming}
          closed={closed}
        />
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
