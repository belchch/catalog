import { useEffect, useRef, useState } from 'react'
import { CheckIcon, CopyIcon, RefreshIcon } from './icons.tsx'

interface MessageCommandsProps {
  /** Text of the parent message — copied verbatim and re-sent on «Повторить». */
  content: string
  /** Re-send handler (typically the chat's `send`). */
  onRepeat?: (content: string) => void
  /** True while a planner response is streaming — disables «Повторить». */
  streaming?: boolean
  /** True when the socket is closed — also disables «Повторить». */
  closed?: boolean
}

/**
 * Command panel rendered under a chat message (CATALOG-10).
 *
 * Two actions:
 *  - «Повторить» — re-sends the same text via `onRepeat`, blocked while a
 *    response is streaming or the connection is closed (no parallel sends).
 *  - «Копировать» — copies `content` to the clipboard with a brief
 *    «Скопировано» confirmation and a legacy fallback for non-secure contexts.
 *
 * Buttons are always visible but muted (text-xs / ink-faint) to stay
 * unobtrusive; they align to the right to match the user-bubble side.
 */
export function MessageCommands({
  content,
  onRepeat,
  streaming = false,
  closed = false,
}: MessageCommandsProps) {
  const [copied, setCopied] = useState(false)
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (resetTimer.current) clearTimeout(resetTimer.current)
    }
  }, [])

  const repeatDisabled = !onRepeat || streaming || closed

  const handleCopy = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(content)
      } else {
        // Legacy fallback for non-secure contexts / older browsers.
        const ta = document.createElement('textarea')
        ta.value = content
        ta.style.position = 'fixed'
        ta.style.opacity = '0'
        document.body.appendChild(ta)
        ta.select()
        document.execCommand('copy')
        document.body.removeChild(ta)
      }
      setCopied(true)
      if (resetTimer.current) clearTimeout(resetTimer.current)
      resetTimer.current = setTimeout(() => setCopied(false), 1500)
    } catch {
      // Silently ignore clipboard errors — the button simply won't confirm.
    }
  }

  const handleRepeat = () => {
    if (repeatDisabled) return
    onRepeat?.(content)
  }

  const repeatLabel = repeatDisabled ? 'Недоступно во время ответа' : 'Переотправить это сообщение'

  return (
    <div className="catalog-message-commands mt-1 flex justify-end gap-0.5 opacity-0 transition-opacity duration-150 group-hover:opacity-100 focus-within:opacity-100 motion-reduce:transition-none">
      <span className="sr-only" role="status" aria-live="polite">
        {copied ? 'Скопировано' : ''}
      </span>
      <button
        type="button"
        className="btn-icon-ghost"
        onClick={handleRepeat}
        disabled={repeatDisabled}
        title={repeatLabel}
        aria-label={repeatLabel}
      >
        <RefreshIcon />
      </button>
      <button
        type="button"
        className="btn-icon-ghost"
        onClick={handleCopy}
        title="Копировать"
        aria-label="Копировать"
      >
        {copied ? <CheckIcon className="text-success" /> : <CopyIcon />}
      </button>
    </div>
  )
}
