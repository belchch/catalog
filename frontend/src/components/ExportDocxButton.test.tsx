import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, exportDocx, type ExportDocxOut } from '../api.ts'
import { ExportDocxButton } from './ExportDocxButton.tsx'

vi.mock('../api.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api.ts')>()
  return {
    ...actual,
    exportDocx: vi.fn(),
  }
})

afterEach(() => {
  cleanup()
})

const OK: ExportDocxOut = {
  ok: true,
  path: 'export/report.docx',
  headings: 2,
  tables: 1,
}

const MISMATCH: ExportDocxOut = {
  ok: false,
  path: 'export/draft.docx',
  headings: 0,
  tables: 1,
}

beforeEach(() => {
  vi.mocked(exportDocx).mockReset()
  vi.mocked(exportDocx).mockResolvedValue(OK)
})

describe('ExportDocxButton', () => {
  it('renders idle and stays enabled', () => {
    render(<ExportDocxButton docIds={['doc-1']} />)
    const button = screen.getByRole('button', { name: 'Выгрузить в docx' }) as HTMLButtonElement
    expect(button.disabled).toBe(false)
    expect(button.getAttribute('aria-busy')).toBeNull()
    expect(screen.queryByRole('status')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('shows loading with busy and disabled, then the path', async () => {
    let resolveExport: (value: ExportDocxOut) => void = () => {}
    vi.mocked(exportDocx).mockImplementation(
      () =>
        new Promise<ExportDocxOut>((resolve) => {
          resolveExport = resolve
        }),
    )
    render(<ExportDocxButton docIds={['doc-1']} title="Отчёт" />)
    const button = screen.getByRole('button', { name: 'Выгрузить в docx' }) as HTMLButtonElement
    fireEvent.click(button)
    expect(button.disabled).toBe(true)
    expect(button.getAttribute('aria-busy')).toBe('true')
    expect(button.textContent).toContain('Выгружаю…')
    fireEvent.click(button)
    expect(exportDocx).toHaveBeenCalledTimes(1)
    expect(exportDocx).toHaveBeenCalledWith({ doc_ids: ['doc-1'], title: 'Отчёт' })
    resolveExport(OK)
    await waitFor(() => {
      expect(screen.getByText('export/report.docx')).toBeTruthy()
    })
    const ready = screen.getByRole('button', { name: 'Выгрузить в docx' }) as HTMLButtonElement
    expect(ready.disabled).toBe(false)
    expect(ready.getAttribute('aria-busy')).toBeNull()
    const status = screen.getByRole('status')
    expect(status.className).toContain('bg-success-soft')
    expect(status.className).toContain('border-success-line')
    expect(status.className).toContain('text-success-ink')
  })

  it('shows API detail on error and allows retry', async () => {
    vi.mocked(exportDocx).mockRejectedValueOnce(
      new ApiError(404, 'Not Found', JSON.stringify({ detail: 'document not found' })),
    )
    render(<ExportDocxButton docIds={['missing']} />)
    fireEvent.click(screen.getByRole('button', { name: 'Выгрузить в docx' }))
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toBe('document not found')
    })
    const alert = screen.getByRole('alert')
    expect(alert.className).toContain('bg-danger-soft')
    expect(alert.className).toContain('border-danger-line')
    expect(alert.className).toContain('text-danger-ink')
    expect(alert.textContent).not.toContain('Ошибка:')
    const button = screen.getByRole('button', { name: 'Выгрузить в docx' }) as HTMLButtonElement
    expect(button.disabled).toBe(false)
    fireEvent.click(button)
    await waitFor(() => {
      expect(screen.getByText('export/report.docx')).toBeTruthy()
    })
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('renders mismatch as warning, not as an error', async () => {
    vi.mocked(exportDocx).mockResolvedValue(MISMATCH)
    render(<ExportDocxButton docIds={['doc-1']} />)
    fireEvent.click(screen.getByRole('button', { name: 'Выгрузить в docx' }))
    await waitFor(() => {
      expect(screen.getByText('export/draft.docx')).toBeTruthy()
    })
    expect(screen.getByText('Записан, но самопроверка не сошлась:')).toBeTruthy()
    const status = screen.getByRole('status')
    expect(status.className).toContain('bg-warning-soft')
    expect(status.className).toContain('border-warning-line')
    expect(status.className).toContain('text-warning-ink')
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('clears path and error when the export target changes', async () => {
    const { rerender } = render(<ExportDocxButton docIds={['doc-1']} />)
    fireEvent.click(screen.getByRole('button', { name: 'Выгрузить в docx' }))
    await waitFor(() => {
      expect(screen.getByText('export/report.docx')).toBeTruthy()
    })
    rerender(<ExportDocxButton docIds={['doc-2']} />)
    expect(screen.queryByText('export/report.docx')).toBeNull()
    expect(screen.queryByRole('status')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('disables with a hint when there are no documents', () => {
    render(<ExportDocxButton docIds={[]} />)
    const button = screen.getByRole('button', { name: 'Выгрузить в docx' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    expect(button.getAttribute('title')).toBe('Нет документов для выгрузки')
    fireEvent.click(button)
    expect(exportDocx).not.toHaveBeenCalled()
  })

  it('uses disabledHint when blocked with documents', () => {
    render(
      <ExportDocxButton
        docIds={['doc-1']}
        disabled
        disabledHint="Дождитесь завершения прогона"
      />,
    )
    const button = screen.getByRole('button', { name: 'Выгрузить в docx' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    expect(button.getAttribute('title')).toBe('Дождитесь завершения прогона')
  })

  it('copies the path and announces confirmation', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    render(<ExportDocxButton docIds={['doc-1']} />)
    fireEvent.click(screen.getByRole('button', { name: 'Выгрузить в docx' }))
    await waitFor(() => {
      expect(screen.getByText('export/report.docx')).toBeTruthy()
    })
    fireEvent.click(screen.getByRole('button', { name: 'Скопировать путь' }))
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith('export/report.docx')
      expect(screen.getByText('Скопировано')).toBeTruthy()
    })
  })

  it('labels a multi-document export', () => {
    render(<ExportDocxButton docIds={['a', 'b']} />)
    const button = screen.getByRole('button', { name: 'Выгрузить документы (2) в docx' })
    expect(button.getAttribute('title')).toBe('Выгрузить документы (2) в docx')
  })
})
