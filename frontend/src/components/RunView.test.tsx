import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DocumentOut } from '../api.ts'
import type { UseRunStreamResult } from '../hooks/useRunStream.ts'
import { RunView } from './RunView.tsx'

afterEach(cleanup)

function runResult(partial: Partial<UseRunStreamResult> = {}): UseRunStreamResult {
  return {
    steps: [],
    meta: null,
    resultText: 'HELLO',
    status: 'ok',
    finished: true,
    outputDocId: null,
    outputDocIds: [],
    artifacts: [],
    cancelling: false,
    closed: false,
    error: null,
    cancel: vi.fn(),
    ...partial,
  }
}

const DOC_A: DocumentOut = {
  id: 'doc-a',
  title: 'Резюме',
  kind: 'result_md',
  created_at: '2026-08-20T00:00:00Z',
}

const DOC_B: DocumentOut = {
  id: 'doc-b',
  title: 'Таблица',
  kind: 'result_md',
  created_at: '2026-08-20T00:00:00Z',
}

function renderRun(partial: Partial<Parameters<typeof RunView>[0]> = {}) {
  const onSaveResult = partial.onSaveResult ?? vi.fn()
  const onOpenDoc = partial.onOpenDoc
  render(
    <RunView
      run={runResult()}
      runId="run-12345678"
      documents={[]}
      onClose={() => {}}
      onSaveResult={onSaveResult}
      savingResult={false}
      {...partial}
    />,
  )
  return { onSaveResult, onOpenDoc }
}

describe('RunView named outputs', () => {
  it('keeps a single-result run without tabs', () => {
    renderRun({
      run: runResult({ resultText: 'HELLO', artifacts: [] }),
    })
    expect(screen.queryByRole('tablist')).toBeNull()
    expect(screen.getByRole('button', { name: 'Сохранить как новый документ' })).toBeTruthy()
    expect(screen.queryByText('Документы прогона')).toBeNull()
    expect(screen.getByText('HELLO')).toBeTruthy()
  })

  it('shows tabs for two artifacts and selects the primary', () => {
    renderRun({
      run: runResult({
        resultText: 'PRIMARY',
        artifacts: [
          { key: 'brief', description: 'Краткое резюме', text: 'PRIMARY' },
          { key: 'table', description: 'Таблица перекодировки', text: 'TABLE' },
        ],
      }),
    })
    const tabs = screen.getAllByRole('tab')
    expect(tabs).toHaveLength(2)
    expect(tabs[0].textContent).toBe('Краткое резюме')
    expect(tabs[0].getAttribute('aria-selected')).toBe('true')
    expect(tabs[1].getAttribute('aria-selected')).toBe('false')
    expect(screen.getByRole('tablist').getAttribute('aria-label')).toBe('Результаты прогона')
    expect(screen.getByText('PRIMARY')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Сохранить как новые документы' })).toBeTruthy()
  })

  it('moves between tabs with arrow keys', () => {
    renderRun({
      run: runResult({
        artifacts: [
          { key: 'brief', description: 'Краткое резюме', text: 'PRIMARY' },
          { key: 'table', description: 'Таблица перекодировки', text: 'TABLE' },
        ],
      }),
    })
    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: 'Таблица перекодировки' }).getAttribute('aria-selected')).toBe(
      'true',
    )
    expect(screen.getByText('TABLE')).toBeTruthy()
    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'Home' })
    expect(screen.getByRole('tab', { name: 'Краткое резюме' }).getAttribute('aria-selected')).toBe('true')
  })

  it('saves the whole batch and then shows chips', () => {
    const onSaveResult = vi.fn()
    const { rerender } = render(
      <RunView
        run={runResult({
          artifacts: [
            { key: 'brief', description: 'Краткое резюме', text: 'PRIMARY' },
            { key: 'table', description: 'Таблица', text: 'TABLE' },
          ],
        })}
        runId="run-1"
        documents={[]}
        onClose={() => {}}
        onSaveResult={onSaveResult}
        savingResult={false}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить как новые документы' }))
    expect(onSaveResult).toHaveBeenCalledWith('run-1')
    rerender(
      <RunView
        run={runResult({
          artifacts: [
            { key: 'brief', description: 'Краткое резюме', text: 'PRIMARY' },
            { key: 'table', description: 'Таблица', text: 'TABLE' },
          ],
        })}
        runId="run-1"
        documents={[DOC_A, DOC_B]}
        onClose={() => {}}
        onSaveResult={onSaveResult}
        savingResult={false}
        savedDocs={[DOC_A, DOC_B]}
        onOpenDoc={() => {}}
      />,
    )
    expect(screen.queryByRole('button', { name: 'Сохранить как новые документы' })).toBeNull()
    expect(screen.getByRole('status').textContent).toContain('Создано 2 документа')
    expect(screen.getByRole('button', { name: 'Резюме · основной' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Таблица' })).toBeTruthy()
  })

  it('opens a document from a chip and closes the run', () => {
    const onOpenDoc = vi.fn()
    renderRun({
      run: runResult({
        artifacts: [
          { key: 'brief', description: 'A', text: '1' },
          { key: 'table', description: 'B', text: '2' },
        ],
        outputDocIds: ['doc-a', 'doc-b'],
        outputDocId: 'doc-a',
      }),
      documents: [DOC_A, DOC_B],
      onOpenDoc,
    })
    fireEvent.click(screen.getByRole('button', { name: 'Резюме · основной' }))
    expect(onOpenDoc).toHaveBeenCalledWith('doc-a')
  })

  it('shows a single created document without chips', () => {
    renderRun({
      run: runResult({
        resultText: 'HELLO',
        artifacts: [],
        outputDocId: 'doc-a',
      }),
      documents: [DOC_A],
    })
    expect(screen.getByText('Документ создан: «Резюме»')).toBeTruthy()
    expect(screen.queryByRole('tablist')).toBeNull()
    expect(screen.queryByText('Документы прогона')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Сохранить как новый документ' })).toBeNull()
  })
})
