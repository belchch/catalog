import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DocumentOut, SkillOut } from '../api.ts'
import type { UseSkillsResult } from '../hooks/useSkills.ts'
import { SkillsPanel } from './SkillsPanel.tsx'

afterEach(cleanup)

function skill(partial: Partial<SkillOut> = {}): SkillOut {
  return {
    id: 'skill-1',
    name: 'Скилл',
    description: null,
    status: 'committed',
    created_at: '2026-08-20T00:00:00Z',
    kind: 'agent',
    tags: ['ai'],
    input_arity: 1,
    provider: null,
    model: null,
    reasoning: null,
    estimated_llm_calls: 1,
    ...partial,
  }
}

function doc(id: string, title: string): DocumentOut {
  return { id, title, kind: 'result_md', created_at: '2026-08-20T00:00:00Z' }
}

function skillsResult(skills: SkillOut[]): UseSkillsResult {
  return {
    skills,
    loading: false,
    error: null,
    refresh: vi.fn(async () => {}),
    commit: vi.fn(async () => {}),
    apply: vi.fn(async () => 'run-1'),
    remove: vi.fn(async () => {}),
    rename: vi.fn(async () => {}),
  }
}

function renderPanel(skills: SkillOut[], documents: DocumentOut[]) {
  render(
    <SkillsPanel
      skills={skillsResult(skills)}
      documents={documents}
      defaultDocId={null}
      onApply={vi.fn()}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
      onRename={vi.fn(async () => {})}
    />,
  )
}

function selectSkill(name: string) {
  fireEvent.click(screen.getByRole('option', { name: `${name}, committed` }))
}

function pickSingleDoc(title: string) {
  fireEvent.click(screen.getByRole('combobox', { name: 'Документ' }))
  fireEvent.click(screen.getByRole('option', { name: title }))
}

function pickMultiDocs(titles: string[]) {
  fireEvent.click(screen.getByRole('combobox', { name: 'Документы' }))
  for (const title of titles) {
    fireEvent.click(screen.getByRole('checkbox', { name: title }))
  }
}

describe('SkillsPanel apply buttons wording (CATALOG-156)', () => {
  it('marks a multi-output skill without promising a single document', () => {
    renderPanel(
      [skill({ id: 's-multi', name: 'МногоВыходов', outputs_count: 3, input_arity: 1 })],
      [doc('d1', 'Документ A')],
    )
    selectSkill('МногоВыходов')
    pickSingleDoc('Документ A')

    const persist = screen.getByRole('button', { name: 'В док · несколько' })
    expect(persist.title).toBe(
      'Результат сразу сохраняется в новые документы; выходов у скилла — 3',
    )
    expect(persist.title).not.toContain('новый документ')

    const preview = screen.getByRole('button', { name: 'На экран' })
    expect(preview.title).toBe(
      'Результат выводится на экран; документы можно сохранить отдельно; выходов у скилла — 3',
    )
    expect(preview.title).not.toContain('документ можно сохранить')
    expect(preview.title).toContain('выходов')
  })

  it('keeps single-output skill wording byte-for-byte unchanged', () => {
    renderPanel(
      [skill({ id: 's-single', name: 'ОдинВыход', outputs_count: 1, input_arity: 1 })],
      [doc('d1', 'Документ A')],
    )
    selectSkill('ОдинВыход')
    pickSingleDoc('Документ A')

    const persist = screen.getByRole('button', { name: 'В док' })
    expect(persist.title).toBe('Результат сразу сохраняется в новый документ')

    const preview = screen.getByRole('button', { name: 'На экран' })
    expect(preview.title).toBe('Результат выводится на экран; документ можно сохранить отдельно')
  })

  it('leaves wording unchanged when outputs_count is absent', () => {
    renderPanel(
      [skill({ id: 's-absent', name: 'БезПоля', outputs_count: undefined, input_arity: 1 })],
      [doc('d1', 'Документ A')],
    )
    selectSkill('БезПоля')
    pickSingleDoc('Документ A')

    expect(screen.getByRole('button', { name: 'В док' }).title).toBe(
      'Результат сразу сохраняется в новый документ',
    )
    expect(screen.getByRole('button', { name: 'На экран' }).title).toBe(
      'Результат выводится на экран; документ можно сохранить отдельно',
    )
  })

  it('keeps exactly one counter in the label when inputs and outputs are both plural', () => {
    renderPanel(
      [skill({ id: 's-both', name: 'ДваИТри', outputs_count: 2, input_arity: null })],
      [doc('d1', 'Документ A'), doc('d2', 'Документ B'), doc('d3', 'Документ C')],
    )
    selectSkill('ДваИТри')
    pickMultiDocs(['Документ A', 'Документ B', 'Документ C'])

    const persist = screen.getByRole('button', { name: 'В док · несколько (3)' })
    expect(persist.title).toContain('выходов у скилла — 2')
    // ровно один счётчик в скобках — суффикс входов, число выходов в подпись не попадает
    expect(persist.textContent?.match(/\(\d+\)/g)).toEqual(['(3)'])

    expect(screen.getByRole('button', { name: 'На экран (3)' })).toBeTruthy()
  })

  it('keeps the single-output suffix behaviour for many inputs', () => {
    renderPanel(
      [skill({ id: 's-single-many', name: 'ОдинВыходМногоВходов', outputs_count: 1, input_arity: null })],
      [doc('d1', 'Документ A'), doc('d2', 'Документ B'), doc('d3', 'Документ C')],
    )
    selectSkill('ОдинВыходМногоВходов')
    pickMultiDocs(['Документ A', 'Документ B', 'Документ C'])

    expect(screen.getByRole('button', { name: 'В док (3)' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'На экран (3)' })).toBeTruthy()
  })

  it('reports a lower-bound count for a collection output', () => {
    renderPanel(
      [
        skill({
          id: 's-collection',
          name: 'Коллекция',
          outputs_count: 3,
          outputs_has_collection: true,
          input_arity: 1,
        }),
      ],
      [doc('d1', 'Документ A')],
    )
    selectSkill('Коллекция')
    pickSingleDoc('Документ A')

    const persist = screen.getByRole('button', { name: 'В док · несколько' })
    expect(persist.title).toContain('3 и более')
  })

  it('marks a single-key collection output (outputs_count: 1) as multiple, not one document', () => {
    renderPanel(
      [
        skill({
          id: 's-single-collection',
          name: 'ПоГлавам',
          outputs_count: 1,
          outputs_has_collection: true,
          input_arity: 1,
        }),
      ],
      [doc('d1', 'Документ A')],
    )
    selectSkill('ПоГлавам')
    pickSingleDoc('Документ A')

    const persist = screen.getByRole('button', { name: 'В док · несколько' })
    expect(persist.title).not.toContain('новый документ')
    expect(persist.title).toContain('1 и более')

    const preview = screen.getByRole('button', { name: 'На экран' })
    expect(preview.title).not.toContain('документ можно сохранить')
    expect(preview.title).toContain('1 и более')
  })
})
