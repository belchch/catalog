import { useEffect, useRef, useState } from 'react'
import {
  exportDocx,
  extractApiDetail,
  type ExportDocxOut,
} from '../api.ts'
import { CheckIcon, CopyIcon, SpinnerIcon } from './icons.tsx'

interface ExportDocxButtonProps {
  docIds: string[]
  title?: string
  disabled?: boolean
  disabledHint?: string
  layout?: 'inline' | 'stacked'
}

type ExportStatus = 'idle' | 'loading' | 'success' | 'error'

export function ExportDocxButton({
  docIds,
  title,
  disabled = false,
  disabledHint,
  layout = 'inline',
}: ExportDocxButtonProps) {
  const [status, setStatus] = useState<ExportStatus>('idle')
  const [result, setResult] = useState<ExportDocxOut | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const requestSeq = useRef(0)
  const targetKey = docIds.join(',')

  useEffect(() => {
    requestSeq.current += 1
    setStatus('idle')
    setResult(null)
    setError(null)
    setCopied(false)
  }, [targetKey])

  useEffect(() => {
    return () => {
      if (resetTimer.current) clearTimeout(resetTimer.current)
    }
  }, [])

  const emptyDocs = docIds.length === 0
  const blocked = disabled || emptyDocs
  const isLoading = status === 'loading'
  const buttonDisabled = blocked || isLoading
  const multiLabel =
    docIds.length > 1 ? `Выгрузить документы (${docIds.length}) в docx` : null
  const actionLabel = multiLabel ?? 'Выгрузить в docx'
  const hint = blocked
    ? emptyDocs
      ? 'Нет документов для выгрузки'
      : (disabledHint ?? 'Нет документов для выгрузки')
    : (multiLabel ?? undefined)

  const handleExport = async () => {
    if (buttonDisabled || emptyDocs) return
    const seq = ++requestSeq.current
    setStatus('loading')
    setResult(null)
    setError(null)
    setCopied(false)
    try {
      const out = await exportDocx({ doc_ids: docIds, title })
      if (seq !== requestSeq.current) return
      setResult(out)
      setStatus('success')
    } catch (e) {
      if (seq !== requestSeq.current) return
      setError(extractApiDetail(e))
      setStatus('error')
    }
  }

  const handleCopy = async () => {
    if (!result?.path) return
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(result.path)
      } else {
        const ta = document.createElement('textarea')
        ta.value = result.path
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
    } catch {}
  }

  const rootClass =
    layout === 'stacked'
      ? 'flex flex-col items-stretch gap-1.5'
      : 'flex flex-wrap items-center gap-2'
  const buttonClass =
    layout === 'stacked' ? 'btn-secondary w-full' : 'btn-secondary'
  const showPath = status === 'success' && result?.path
  const mismatch = Boolean(showPath && result && !result.ok)

  return (
    <div className={rootClass}>
      <button
        type="button"
        className={buttonClass}
        disabled={buttonDisabled}
        aria-busy={isLoading || undefined}
        aria-label={actionLabel}
        title={hint}
        onClick={() => void handleExport()}
      >
        {isLoading && <SpinnerIcon className="mr-1.5 size-3.5" />}
        {isLoading ? 'Выгружаю…' : 'Выгрузить в docx'}
      </button>
      {showPath && result && (
        <span
          role="status"
          aria-live="polite"
          className={
            'inline-flex items-center gap-1.5 rounded-control border px-2 py-1 text-[11px] ' +
            (mismatch
              ? 'border-warning-line bg-warning-soft text-warning-ink'
              : 'border-success-line bg-success-soft text-success-ink')
          }
        >
          {mismatch && (
            <span>Записан, но самопроверка не сошлась:</span>
          )}
          <code
            className={
              layout === 'stacked'
                ? 'font-mono break-all'
                : 'min-w-0 truncate font-mono'
            }
            title={layout === 'inline' ? result.path : undefined}
          >
            {result.path}
          </code>
          <button
            type="button"
            className="btn-icon-ghost size-6"
            onClick={() => void handleCopy()}
            aria-label="Скопировать путь"
          >
            {copied ? <CheckIcon className="text-success" /> : <CopyIcon />}
          </button>
        </span>
      )}
      {copied && (
        <span className="sr-only" role="status" aria-live="polite">
          Скопировано
        </span>
      )}
      {status === 'error' && error && (
        <p
          role="alert"
          className={
            'rounded-control border border-danger-line bg-danger-soft px-2 py-1 text-[11px] text-danger-ink break-words' +
            (layout === 'inline' ? ' basis-full' : '')
          }
        >
          {error}
        </p>
      )}
    </div>
  )
}
