import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DocumentOut } from '../api.ts'
import type { PlannerMessage } from '../hooks/usePlannerSession.ts'
import { Chat } from './Chat.tsx'

afterEach(cleanup)

function doc(id: string, title: string, kind = 'docx'): DocumentOut {
  return { id, title, kind, created_at: '2026-01-01T00:00:00Z' }
}

const SPEC = doc('d1', 'Spec.docx')

function renderChat(overrides: Partial<Parameters<typeof Chat>[0]> = {}) {
  const onSend = vi.fn<(text: string, docIds?: string[], docs?: DocumentOut[]) => void>()
  const onRemoveDocument = vi.fn<(docId: string) => void>()
  const onOpenTools = vi.fn<() => void>()
  render(
    <Chat
      messages={[]}
      streaming={false}
      cancelling={false}
      closed={false}
      reconnecting={false}
      error={null}
      suggestions={[]}
      documents={[SPEC]}
      sessionDocuments={[]}
      sessionId="s1"
      onSend={onSend}
      onCancel={() => {}}
      onReconnect={() => {}}
      onRemoveDocument={onRemoveDocument}
      onCreateSkill={() => {}}
      buildingSkill={false}
      proposingTracks={false}
      editingSkillName={null}
      buildError={null}
      buildErrorIsTimeout={false}
      sessionTimeoutSeconds={60}
      onOpenTimeoutModal={() => {}}
      onDismissBuildError={() => {}}
      onOpenTools={onOpenTools}
      {...overrides}
    />,
  )
  return { onSend, onRemoveDocument, onOpenTools }
}

function selectDoc(title: string) {
  fireEvent.click(screen.getByRole('combobox', { name: 'Добавить документ' }))
  fireEvent.click(screen.getByRole('checkbox', { name: title }))
}

describe('Chat composer', () => {
  it('sends selected docs with a suggestion and clears them for the next click', () => {
    const { onSend } = renderChat()
    selectDoc('Spec.docx')
    expect(screen.getByText('DOCX · к отправке')).toBeTruthy()

    const chip = screen.getByRole('button', { name: 'Изучи доступные документы' })
    fireEvent.click(chip)
    expect(onSend).toHaveBeenCalledTimes(1)
    expect(onSend).toHaveBeenCalledWith('Изучи доступные документы', ['d1'], [SPEC])
    expect(screen.queryByText('DOCX · к отправке')).toBeNull()

    fireEvent.click(chip)
    expect(onSend).toHaveBeenCalledTimes(2)
    expect(onSend.mock.calls[1][0]).toBe('Изучи доступные документы')
    expect(onSend.mock.calls[1][1]).toBeUndefined()
    expect(onSend.mock.calls[1][2]).toBeUndefined()
  })

  it('repeats a user message without composer docs and keeps the selection', () => {
    const messages: PlannerMessage[] = [{ role: 'user', content: 'hello' }]
    const { onSend } = renderChat({ messages, suggestions: ['ещё раз'] })
    selectDoc('Spec.docx')
    expect(screen.getByText('DOCX · к отправке')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Переотправить это сообщение' }))
    expect(onSend).toHaveBeenCalledTimes(1)
    expect(onSend).toHaveBeenCalledWith('hello')
    expect(onSend.mock.calls[0]).toHaveLength(1)
    expect(screen.getByText('DOCX · к отправке')).toBeTruthy()
  })

  it('submits typed text together with selected docs', () => {
    const { onSend } = renderChat()
    selectDoc('Spec.docx')
    const textarea = screen.getByPlaceholderText('Сообщение планировщику…')
    fireEvent.change(textarea, { target: { value: 'посмотри spec' } })
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }))
    expect(onSend).toHaveBeenCalledWith('посмотри spec', ['d1'], [SPEC])
    expect(screen.queryByText('Spec.docx')).toBeNull()
  })

  it('shows a document once when it is both selected and already in the session', () => {
    renderChat({ sessionDocuments: [SPEC] })
    selectDoc('Spec.docx')
    const cards = screen.getAllByRole('listitem')
    expect(cards).toHaveLength(1)
    expect(screen.getByText('DOCX')).toBeTruthy()
    expect(screen.queryByText('DOCX · к отправке')).toBeNull()
  })

  it('exposes the document picker on + and the tools slot without a popover', () => {
    const onOpenTools = vi.fn()
    renderChat({ onOpenTools, attachedSkillCount: 2 })
    expect(screen.getByRole('combobox', { name: 'Добавить документ' })).toBeTruthy()
    expect(screen.queryByText('Документы в сессии')).toBeNull()
    expect(screen.queryByText('Создать скилл из сессии')).toBeNull()
    expect(screen.getByText('Чат планировщика')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Создать скилл' }).hasAttribute('disabled')).toBe(
      true,
    )

    const tools = screen.getByRole('button', { name: 'Инструменты, включено 2' })
    expect(tools.getAttribute('aria-expanded')).toBeNull()
    expect(tools.getAttribute('aria-haspopup')).toBeNull()
    expect(tools.textContent).toContain('2')
    fireEvent.click(tools)
    expect(onOpenTools).toHaveBeenCalledTimes(1)
  })

  it('hides the tools badge when the count is zero', () => {
    renderChat({ attachedSkillCount: 0 })
    const tools = screen.getByRole('button', { name: 'Инструменты' })
    expect(tools.textContent).not.toMatch(/\d/)
  })
})
