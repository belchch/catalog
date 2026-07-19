import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

type ViewMode = 'md' | 'text'

interface MarkdownViewProps {
  text: string
  defaultMode?: ViewMode
  className?: string
}

export function MarkdownView({
  text,
  defaultMode = 'md',
  className,
}: MarkdownViewProps) {
  const [mode, setMode] = useState<ViewMode>(defaultMode)

  return (
    <div>
      <div
        role="group"
        aria-label="Режим отображения"
        className="mb-1 flex justify-end gap-1"
      >
        <button
          type="button"
          aria-pressed={mode === 'md'}
          className={
            'rounded px-1.5 py-0.5 text-[10px] focus:outline-none focus:ring-1 focus:ring-indigo-500 ' +
            (mode === 'md'
              ? 'bg-indigo-600 text-white'
              : 'bg-slate-800 text-slate-300')
          }
          onClick={() => setMode('md')}
        >
          md
        </button>
        <button
          type="button"
          aria-pressed={mode === 'text'}
          className={
            'rounded px-1.5 py-0.5 text-[10px] focus:outline-none focus:ring-1 focus:ring-indigo-500 ' +
            (mode === 'text'
              ? 'bg-indigo-600 text-white'
              : 'bg-slate-800 text-slate-300')
          }
          onClick={() => setMode('text')}
        >
          text
        </button>
      </div>
      {mode === 'md' ? (
        <div className={'md-body overflow-x-auto' + (className ? ` ${className}` : '')}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        </div>
      ) : (
        <pre
          className={
            'whitespace-pre-wrap break-words font-mono' +
            (className ? ` ${className}` : '')
          }
        >
          {text}
        </pre>
      )}
    </div>
  )
}
