import type { PlannerMessage } from '../hooks/usePlannerSession.ts'
import { MarkdownView } from './MarkdownView.tsx'
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
      <div className="catalog-message catalog-message--user my-4 flex flex-col items-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm">
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
      <div className="catalog-message catalog-message--tool my-2 text-xs text-ink-faint">
        <span className="font-mono">ℹ {message.content}</span>
      </div>
    )
  }
  return (
    <div className="catalog-message catalog-message--assistant my-4 flex justify-start">
      <div className="max-w-[88%] px-1 py-1">
        <MarkdownView
          text={message.content}
          defaultMode="md"
          className="text-sm text-ink"
        />
      </div>
    </div>
  )
}
