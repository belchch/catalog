import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SkillOut } from '../api.ts'
import { ToolsPopover } from './ToolsPopover.tsx'

afterEach(cleanup)

function skill(partial: Partial<SkillOut> & Pick<SkillOut, 'id' | 'name'>): SkillOut {
  return {
    description: null,
    status: 'committed',
    created_at: '2026-01-01T00:00:00Z',
    kind: 'script',
    tags: [],
    input_arity: 1,
    provider: null,
    model: null,
    reasoning: null,
    estimated_llm_calls: 0,
    ...partial,
  }
}

const EXTRACT = skill({
  id: 's1',
  name: 'Extract',
  description: 'Достаёт тезисы',
  tags: ['python'],
})
const SUMMARIZE = skill({
  id: 's2',
  name: 'Summarize',
  description: 'Краткое изложение',
  kind: 'agent',
  tags: ['ai'],
  estimated_llm_calls: 4,
})
const PIPE = skill({
  id: 's3',
  name: 'Pipeline',
  kind: 'pipeline',
  tags: ['python', 'ai'],
  estimated_llm_calls: 6,
})

function renderPopover(overrides: Partial<Parameters<typeof ToolsPopover>[0]> = {}) {
  const onClose = vi.fn()
  const onToggle = vi.fn()
  const onCreateSkill = vi.fn()
  render(
    <ToolsPopover
      open
      onClose={onClose}
      skills={[EXTRACT, SUMMARIZE, PIPE]}
      attachedIds={['s1']}
      onToggle={onToggle}
      onCreateSkill={onCreateSkill}
      {...overrides}
    />,
  )
  return { onClose, onToggle, onCreateSkill }
}

describe('ToolsPopover', () => {
  it('renders header, search, grouped rows and footer', () => {
    renderPopover()
    expect(screen.getByRole('dialog', { name: 'Инструменты сессии' })).toBeTruthy()
    expect(screen.getByText('Инструменты')).toBeTruthy()
    expect(screen.getByText('Планировщик может вызывать включённые скиллы')).toBeTruthy()
    expect(screen.getByRole('searchbox', { name: 'Поиск инструментов' })).toBeTruthy()
    expect(screen.getByText('Включены')).toBeTruthy()
    expect(screen.getByText('Доступны')).toBeTruthy()
    expect(screen.getByText('Extract')).toBeTruthy()
    expect(screen.getByText('Достаёт тезисы')).toBeTruthy()
    expect(screen.getByText('script · без LLM')).toBeTruthy()
    expect(screen.getAllByText('python').length).toBeGreaterThan(0)
    expect(screen.getByText('Summarize')).toBeTruthy()
    expect(screen.getByText('agent · до 4 LLM-вызовов')).toBeTruthy()
    expect(screen.getByText('pipeline · до 6 LLM-вызовов')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Создать скилл' })).toBeTruthy()
  })

  it('hides group headers when only one group is present', () => {
    renderPopover({ attachedIds: [] })
    expect(screen.queryByText('Включены')).toBeNull()
    expect(screen.queryByText('Доступны')).toBeNull()
  })

  it('keeps attached skills first after search', () => {
    renderPopover({
      skills: [SUMMARIZE, EXTRACT],
      attachedIds: ['s1'],
    })
    fireEvent.change(screen.getByRole('searchbox', { name: 'Поиск инструментов' }), {
      target: { value: 'e' },
    })
    const items = screen.getAllByRole('listitem')
    const texts = items.map((el) => el.textContent ?? '')
    const extractIdx = texts.findIndex((t) => t.includes('Extract'))
    const summarizeIdx = texts.findIndex((t) => t.includes('Summarize'))
    expect(extractIdx).toBeGreaterThanOrEqual(0)
    expect(summarizeIdx).toBeGreaterThan(extractIdx)
  })

  it('filters by name and description and can reset', () => {
    renderPopover()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Поиск инструментов' }), {
      target: { value: 'тезис' },
    })
    expect(screen.getByText('Extract')).toBeTruthy()
    expect(screen.queryByText('Summarize')).toBeNull()

    fireEvent.change(screen.getByRole('searchbox', { name: 'Поиск инструментов' }), {
      target: { value: 'нет такого' },
    })
    expect(screen.getByText('Ничего не найдено')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Сбросить' }))
    expect(screen.getByText('Summarize')).toBeTruthy()
    expect(
      (screen.getByRole('searchbox', { name: 'Поиск инструментов' }) as HTMLInputElement)
        .value,
    ).toBe('')
  })

  it('shows empty and loading copy while keeping the footer', () => {
    const { rerender } = render(
      <ToolsPopover
        open
        onClose={() => {}}
        skills={[]}
        attachedIds={[]}
        onToggle={() => {}}
        onCreateSkill={() => {}}
      />,
    )
    expect(
      screen.getByText('Скиллов пока нет — создайте из сессии планировщика'),
    ).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Создать скилл' })).toBeTruthy()

    rerender(
      <ToolsPopover
        open
        onClose={() => {}}
        skills={[]}
        attachedIds={[]}
        onToggle={() => {}}
        onCreateSkill={() => {}}
        loading
      />,
    )
    expect(screen.getByText('Загрузка…')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Создать скилл' })).toBeTruthy()
  })

  it('shows an error alert without hiding the list', () => {
    renderPopover({ error: 'Сеть недоступна' })
    expect(screen.getByRole('alert').textContent).toBe('Сеть недоступна')
    expect(screen.getByText('Extract')).toBeTruthy()
  })

  it('toggles any kind and only blocks pending rows', () => {
    const { onToggle } = renderPopover({ pendingIds: ['s1'] })
    const pendingSwitch = screen.getByRole('switch', { name: 'Отключить Extract' })
    expect(pendingSwitch.hasAttribute('disabled')).toBe(true)
    expect(pendingSwitch.getAttribute('title')).toBe('Применяем…')
    expect(pendingSwitch.getAttribute('aria-description')).toBe('Применяем…')
    expect(screen.getByText('Extract').closest('li')?.getAttribute('aria-busy')).toBe(
      'true',
    )

    const agentSwitch = screen.getByRole('switch', {
      name: 'Включить Summarize как инструмент',
    })
    expect(agentSwitch.hasAttribute('disabled')).toBe(false)
    expect(agentSwitch.getAttribute('title')).toBeNull()
    fireEvent.click(agentSwitch)
    expect(onToggle).toHaveBeenCalledWith('s2', true)

    const pipelineSwitch = screen.getByRole('switch', {
      name: 'Включить Pipeline как инструмент',
    })
    expect(pipelineSwitch.hasAttribute('disabled')).toBe(false)
    expect(pipelineSwitch.getAttribute('title')).toBeNull()
    fireEvent.click(pipelineSwitch)
    expect(onToggle).toHaveBeenCalledWith('s3', true)
    expect(screen.queryByText('Инструментом может стать только script-скилл')).toBeNull()
  })

  it('shows singular cost and omits zero estimate for non-script skills', () => {
    const once = skill({
      id: 's5',
      name: 'Once',
      kind: 'agent',
      estimated_llm_calls: 1,
    })
    const free = skill({
      id: 's6',
      name: 'Free',
      kind: 'pipeline',
      estimated_llm_calls: 0,
    })
    renderPopover({
      skills: [EXTRACT, once, free],
      attachedIds: [],
    })
    expect(screen.getByText('agent · до 1 LLM-вызова')).toBeTruthy()
    const freeRow = screen.getByText('Free').closest('li')
    expect(freeRow?.textContent).toMatch(/pipeline/)
    expect(freeRow?.textContent).not.toContain('до 0')
    expect(freeRow?.textContent).not.toContain('без LLM')
  })

  it('calls onToggle for an available script skill', () => {
    const extra = skill({ id: 's4', name: 'Clean', tags: ['python'] })
    const { onToggle } = renderPopover({
      skills: [EXTRACT, extra],
      attachedIds: ['s1'],
    })
    fireEvent.click(screen.getByRole('switch', { name: 'Включить Clean как инструмент' }))
    expect(onToggle).toHaveBeenCalledWith('s4', true)
  })

  it('renders badges in python-then-ai order and omits the chevron without a handler', () => {
    renderPopover({ attachedIds: ['s3'], onOpenSkillCard: undefined })
    const row = screen.getByText('Pipeline').closest('li')
    expect(row).toBeTruthy()
    const badges = Array.from(row!.querySelectorAll('.badge-info, .badge-accent')).map(
      (el) => el.textContent,
    )
    expect(badges).toEqual(['python', 'ai'])
    expect(screen.queryByRole('button', { name: 'Открыть карточку Pipeline' })).toBeNull()
  })

  it('closes on chevron and create-skill', () => {
    const onOpenSkillCard = vi.fn()
    const { onClose, onCreateSkill } = renderPopover({ onOpenSkillCard })
    fireEvent.click(screen.getByRole('button', { name: 'Открыть карточку Extract' }))
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onOpenSkillCard).toHaveBeenCalledWith('s1')

    fireEvent.click(screen.getByRole('button', { name: 'Создать скилл' }))
    expect(onClose).toHaveBeenCalledTimes(2)
    expect(onCreateSkill).toHaveBeenCalledTimes(1)
  })

  it('does not render when closed', () => {
    renderPopover({ open: false })
    expect(screen.queryByRole('dialog', { name: 'Инструменты сессии' })).toBeNull()
  })
})
