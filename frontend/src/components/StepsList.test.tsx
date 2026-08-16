import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { PipelineStepDraft } from '../api.ts'
import { StepsList } from './StepsList.tsx'

function draft(partial: Partial<PipelineStepDraft> = {}): PipelineStepDraft {
  return {
    id: 'step',
    type: 'script',
    input: 'previous',
    code: '',
    system_prompt: '',
    allowed_tools: [],
    model: '',
    provider: '',
    reasoning: '',
    skill_id: '',
    skill_name: '',
    config_hash: '',
    skill_kind: '',
    ...partial,
  }
}

function openDetails(name: string) {
  const row = screen.getByText(name).closest('li')
  const summary = row?.querySelector('summary')
  if (!summary) throw new Error('details summary missing')
  fireEvent.click(summary)
  return row
}

afterEach(cleanup)

describe('StepsList', () => {
  it('shows a SKILL badge and snapshot details without code or prompt hints', () => {
    render(
      <StepsList
        steps={[
          draft({
            id: 'call_summary',
            type: 'skill',
            skill_id: 'sk_7f3',
            skill_name: 'Сводка',
            skill_kind: 'agent',
            config_hash: '1a2b3c4dffffeeee',
          }),
        ]}
      />,
    )
    expect(screen.getByText('SKILL')).toBeTruthy()
    expect(screen.getByText('SKILL').className).toContain('badge-success')
    expect(screen.queryByText('SCRIPT')).toBeNull()
    expect(screen.queryByText('LLM')).toBeNull()
    const row = openDetails('call_summary')
    expect(row?.textContent).toContain('Сводка · agent')
    const pin = screen.getByText('1a2b3c4d')
    expect(pin.getAttribute('title')).toBe('1a2b3c4dffffeeee')
    expect(row?.textContent).not.toContain('код не задан')
    expect(row?.textContent).not.toContain('промпт не задан')
    expect(row?.textContent).not.toContain('allowed_tools')
    expect(row?.textContent).not.toContain('по умолчанию скила')
  })

  it('shows skill_id and a build hint for a draft without a snapshot', () => {
    render(
      <StepsList
        steps={[draft({ id: 'call', type: 'skill', skill_id: 'sk_draft_long' })]}
      />,
    )
    const row = openDetails('call')
    expect(row?.textContent).toContain('id: sk_draft_long')
    expect(row?.textContent).toContain('имя и пин появятся при сборке')
  })

  it('warns when skill_id is empty', () => {
    render(<StepsList steps={[draft({ id: 'empty', type: 'skill' })]} />)
    const row = openDetails('empty')
    expect(row?.textContent).toContain('скилл не выбран')
    expect(row?.textContent).not.toContain('код не задан')
    expect(row?.textContent).not.toContain('промпт не задан')
  })

  it('does not let a skill step steal first-empty hints from neighbors', () => {
    render(
      <StepsList
        steps={[
          draft({ id: 'call', type: 'skill', skill_id: 'sk_1' }),
          draft({ id: 'extract', type: 'script' }),
          draft({ id: 'note', type: 'llm' }),
        ]}
      />,
    )
    const skill = openDetails('call')
    expect(skill?.textContent).toContain('имя и пин появятся при сборке')
    expect(skill?.textContent).not.toContain('код не задан')
    expect(skill?.textContent).not.toContain('промпт не задан')
    const script = openDetails('extract')
    expect(script?.textContent).toContain('код возьмётся из артефакта Script при сборке')
    const llm = openDetails('note')
    expect(llm?.textContent).toContain('промпт возьмётся из артефакта Prompt при сборке')
  })
})
