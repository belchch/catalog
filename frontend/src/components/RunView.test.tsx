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

describe('RunView collection outputs', () => {
  function chapterArtifacts(n: number) {
    return [
      { key: 'index', description: 'Оглавление', text: 'INDEX' },
      {
        key: 'chapters',
        description: 'Главы',
        text: Array.from({ length: n }, (_, i) => `# Глава ${i + 1}\n\ntext ${i + 1}`),
      },
    ]
  }

  it('groups a 7-chapter collection output into two tabs, not eight', () => {
    renderRun({
      run: runResult({ artifacts: chapterArtifacts(7) }),
    })
    const tabs = screen.getAllByRole('tab')
    expect(tabs).toHaveLength(2)
    expect(tabs[1].textContent).toBe('Главы · 7')
    expect(screen.getByRole('button', { name: 'Сохранить как 8 документов' })).toBeTruthy()
  })

  it('moves keyboard focus across the two output tabs, not the seven chapters', () => {
    renderRun({
      run: runResult({ artifacts: chapterArtifacts(7) }),
    })
    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: 'Главы · 7' }).getAttribute('aria-selected')).toBe(
      'true',
    )
    expect(screen.getByText('элементов: 7')).toBeTruthy()
    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: 'Оглавление' }).getAttribute('aria-selected')).toBe(
      'true',
    )
  })

  it('expands the first chapter and keeps the rest collapsed and unmounted', () => {
    renderRun({
      run: runResult({ artifacts: chapterArtifacts(3) }),
    })
    fireEvent.click(screen.getByRole('tab', { name: 'Главы · 3' }))
    expect(screen.getByText('text 1')).toBeTruthy()
    expect(screen.queryByText('text 2')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '2. Глава 2' }))
    expect(screen.getByText('text 2')).toBeTruthy()
  })

  it('shows a single collection output without a tablist', () => {
    renderRun({
      run: runResult({
        artifacts: [
          { key: 'chapters', description: 'Главы', text: ['# Глава 1\n\ntext 1', 'text 2'] },
        ],
      }),
    })
    expect(screen.queryByRole('tablist')).toBeNull()
    expect(screen.getByText('элементов: 2')).toBeTruthy()
    expect(screen.getByText('text 1')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Сохранить как 2 документа' })).toBeTruthy()
  })

  it('renders a run without collections exactly as before', () => {
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
    expect(tabs[0].textContent).toBe('Краткое резюме')
    expect(screen.getByRole('button', { name: 'Сохранить как новые документы' })).toBeTruthy()
    expect(screen.queryByText(/элементов:/)).toBeNull()
  })

  it('collapses the created-docs chip list beyond the six-chip limit', () => {
    const docs = Array.from({ length: 8 }, (_, i) => ({
      id: `doc-${i}`,
      title: `Глава ${i + 1}`,
      kind: 'result_md',
      created_at: '2026-08-20T00:00:00Z',
    }))
    renderRun({
      run: runResult({
        artifacts: chapterArtifacts(7),
        outputDocIds: docs.map((d) => d.id),
      }),
      documents: docs,
    })
    expect(screen.getByRole('status').textContent).toContain('Создано 8 документов')
    expect(screen.queryByRole('button', { name: 'Глава 1' })).toBeNull()
    const toggle = screen.getByRole('button', { name: 'Показать 8 документов' })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(toggle)
    expect(screen.getByRole('button', { name: 'Скрыть список' })).toBeTruthy()
    expect(screen.getByText('Глава 1')).toBeTruthy()
  })
})
