import { useEffect, useId, useRef } from 'react'
import type { ScanReport } from '../api.ts'
import { ScanReportView } from './ScanReportView.tsx'

interface RescanReportModalProps {
  report: ScanReport
  onClose: () => void
}

export function RescanReportModal({ report, onClose }: RescanReportModalProps) {
  const titleId = useId()
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeRef.current?.focus()
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="modal-overlay">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="modal-card max-w-lg"
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 id={titleId} className="text-sm font-semibold text-ink">
            Отчёт пересканирования
          </h2>
          <button
            ref={closeRef}
            type="button"
            className="btn-ghost px-1"
            onClick={onClose}
            aria-label="Закрыть"
          >
            ✕
          </button>
        </div>
        <ScanReportView report={report} />
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" className="btn-primary" onClick={onClose}>
            Готово
          </button>
        </div>
      </div>
    </div>
  )
}
