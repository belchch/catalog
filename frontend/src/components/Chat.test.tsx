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
      interrupted={false}
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

  it('sends the suggestion text and drops a typed draft', () => {
    const { onSend } = renderChat()
    const textarea = screen.getByPlaceholderText('Сообщение планировщику…')
    fireEvent.change(textarea, { target: { value: 'черновик' } })

    fireEvent.click(screen.getByRole('button', { name: 'Опиши задачу для скилла' }))

    expect(onSend).toHaveBeenCalledWith('Опиши задачу для скилла', undefined, undefined)
    expect((textarea as HTMLTextAreaElement).value).toBe('')
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

  it('exposes the document picker on + and a closed tools trigger', () => {
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
    expect(tools.hasAttribute('disabled')).toBe(false)
    expect(tools.getAttribute('title')).toBe('Инструменты')
    expect(tools.getAttribute('aria-description')).toBeNull()
    expect(tools.getAttribute('aria-expanded')).toBe('false')
    expect(tools.getAttribute('aria-haspopup')).toBe('dialog')
    expect(tools.getAttribute('aria-controls')).toBeTruthy()
    expect(tools.textContent).toContain('2')
    expect(screen.queryByRole('dialog', { name: 'Инструменты сессии' })).toBeNull()
    fireEvent.click(tools)
    expect(onOpenTools).toHaveBeenCalledTimes(1)
  })

  it('hides the tools badge when the count is zero', () => {
    renderChat({ attachedSkillCount: 0 })
    const tools = screen.getByRole('button', { name: 'Инструменты' })
    expect(tools.textContent).not.toMatch(/\d/)
  })

  it('opens the tools popover and closes it on Escape', () => {
    const onCloseTools = vi.fn()
    renderChat({
      toolsOpen: true,
      onCloseTools,
      availableSkills: [
        {
          id: 'sk1',
          name: 'Extract',
          description: 'Тезисы',
          status: 'committed',
          created_at: '2026-01-01T00:00:00Z',
          kind: 'script',
          tags: ['python'],
          input_arity: 1,
          provider: null,
          model: null,
          reasoning: null,
          estimated_llm_calls: 0,
        },
      ],
      attachedSkillIds: ['sk1'],
      attachedSkillCount: 1,
    })
    expect(screen.getByRole('dialog', { name: 'Инструменты сессии' })).toBeTruthy()
    const tools = screen.getByRole('button', { name: 'Инструменты, включено 1' })
    expect(tools.getAttribute('aria-expanded')).toBe('true')
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onCloseTools).toHaveBeenCalledTimes(1)
  })

  it('closes the tools popover when generation starts', () => {
    const onCloseTools = vi.fn()
    renderChat({ toolsOpen: true, onCloseTools, streaming: true })
    expect(onCloseTools).toHaveBeenCalled()
  })

  it('explains a disabled tools button without a session', () => {
    renderChat({ sessionId: null })
    const tools = screen.getByRole('button', { name: 'Инструменты' })
    expect(tools.hasAttribute('disabled')).toBe(true)
    expect(tools.getAttribute('title')).toBe(
      'Отправьте сообщение, чтобы начать сессию',
    )
    expect(tools.getAttribute('aria-description')).toBe(
      'Отправьте сообщение, чтобы начать сессию',
    )
  })

  it('explains a disabled tools button while streaming', () => {
    renderChat({ streaming: true, sessionId: null })
    const tools = screen.getByRole('button', { name: 'Инструменты' })
    expect(tools.hasAttribute('disabled')).toBe(true)
    expect(tools.getAttribute('title')).toBe('Идёт генерация')
    expect(tools.getAttribute('aria-description')).toBe('Идёт генерация')
  })
})

describe('Chat connection banner', () => {
  it('hides the thinking indicator when the socket is closed even if streaming is stuck', () => {
    renderChat({ streaming: true, closed: true, interrupted: true })
    expect(screen.queryByText(/планировщик думает/)).toBeNull()
    expect(screen.getByText('Соединение потеряно — ответ прерван')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Остановить генерацию' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Отправить' })).toBeTruthy()
  })

  it('shows the interrupted banner with reconnect and a draft-preserving composer', () => {
    const onReconnect = vi.fn()
    const { onSend } = renderChat({
      closed: true,
      interrupted: true,
      onReconnect,
    })
    const status = screen.getByRole('status')
    expect(status.getAttribute('aria-live')).toBe('polite')
    expect(status.className).toContain('border-warning-line')
    expect(status.className).toContain('bg-warning-soft')
    expect(status.className).toContain('text-warning-ink')
    expect(status.className).not.toMatch(/#[0-9a-fA-F]{3,8}/)
    expect(status.textContent).toContain('Соединение потеряно — ответ прерван')
    expect(status.textContent).toContain(
      'Часть ответа могла не сохраниться. Переподключитесь и повторите запрос.',
    )
    const reconnect = screen.getByRole('button', { name: 'Переподключить' })
    expect(reconnect.hasAttribute('disabled')).toBe(false)
    expect(reconnect.className).toContain('btn-secondary')
    fireEvent.click(reconnect)
    expect(onReconnect).toHaveBeenCalledTimes(1)

    const textarea = screen.getByPlaceholderText('Сообщение планировщику…')
    fireEvent.change(textarea, { target: { value: 'черновик' } })
    fireEvent.keyDown(textarea, { key: 'Enter' })
    expect(onSend).not.toHaveBeenCalled()
    expect((textarea as HTMLTextAreaElement).value).toBe('черновик')
    expect(textarea.hasAttribute('disabled')).toBe(false)

    const send = screen.getByRole('button', { name: 'Отправить' })
    expect(send.hasAttribute('disabled')).toBe(true)
    expect(send.getAttribute('title')).toBe('Нет соединения — переподключитесь')
    expect(send.getAttribute('aria-description')).toBe(
      'Нет соединения — переподключитесь',
    )
    fireEvent.click(send)
    expect(onSend).not.toHaveBeenCalled()

    const chip = screen.getByRole('button', { name: 'Изучи доступные документы' })
    expect(chip.hasAttribute('disabled')).toBe(true)
    fireEvent.click(chip)
    expect(onSend).not.toHaveBeenCalled()
  })

  it('shows the idle disconnect banner without the interrupted copy', () => {
    renderChat({ closed: true, interrupted: false })
    const status = screen.getByRole('status')
    expect(status.textContent).toContain('Соединение потеряно')
    expect(status.textContent).not.toContain('ответ прерван')
    expect(status.textContent).toContain('Отправка сообщений недоступна.')
    expect(screen.getByRole('button', { name: 'Переподключить' })).toBeTruthy()
  })

  it('shows a busy reconnecting banner and keeps send blocked', () => {
    const onReconnect = vi.fn()
    const { onSend } = renderChat({
      reconnecting: true,
      interrupted: false,
      onReconnect,
    })
    const status = screen.getByRole('status')
    expect(status.getAttribute('aria-busy')).toBe('true')
    expect(status.textContent).toContain('Переподключаю…')
    expect(status.textContent).not.toContain('Соединение потеряно')
    const reconnect = screen.getByRole('button', { name: 'Переподключаю…' })
    expect(reconnect.hasAttribute('disabled')).toBe(true)
    expect(reconnect.getAttribute('aria-busy')).toBe('true')
    fireEvent.click(reconnect)
    expect(onReconnect).not.toHaveBeenCalled()

    const send = screen.getByRole('button', { name: 'Отправить' })
    expect(send.getAttribute('title')).toBe('Нет соединения — переподключитесь')
    fireEvent.click(send)
    expect(onSend).not.toHaveBeenCalled()
  })

  it('renders the banner after the last message and hides it when an error is shown', () => {
    const messages: PlannerMessage[] = [{ role: 'user', content: 'hello' }]
    renderChat({ messages, closed: true, interrupted: true })
    const heading = screen.getByText('Соединение потеряно — ответ прерван')
    const status = heading.closest('[role="status"]')
    expect(status).toBeTruthy()
    const content = status?.parentElement
    expect(content?.textContent).toMatch(/hello[\s\S]*Соединение потеряно/)
    const errorSlot = content?.querySelector('.text-danger-ink')
    expect(errorSlot).toBeNull()
    const bannerIndex = content?.textContent?.indexOf('Соединение потеряно') ?? -1
    const helloIndex = content?.textContent?.indexOf('hello') ?? -1
    expect(helloIndex).toBeGreaterThan(-1)
    expect(bannerIndex).toBeGreaterThan(helloIndex)
    cleanup()
    renderChat({ messages, closed: true, interrupted: true, error: 'boom' })
    expect(screen.queryByText('Соединение потеряно — ответ прерван')).toBeNull()
    expect(screen.getByText('Ошибка: boom')).toBeTruthy()
  })

  it('restores composer focus after a click-initiated reconnect', () => {
    const onReconnect = vi.fn()
    const view = render(
      <Chat
        messages={[]}
        streaming={false}
        cancelling={false}
        closed={true}
        reconnecting={false}
        interrupted={true}
        error={null}
        suggestions={[]}
        documents={[SPEC]}
        sessionDocuments={[]}
        sessionId="s1"
        onSend={() => {}}
        onCancel={() => {}}
        onReconnect={onReconnect}
        onCreateSkill={() => {}}
        buildingSkill={false}
        proposingTracks={false}
        editingSkillName={null}
        buildError={null}
        buildErrorIsTimeout={false}
        sessionTimeoutSeconds={60}
        onOpenTimeoutModal={() => {}}
        onDismissBuildError={() => {}}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Переподключить' }))
    expect(onReconnect).toHaveBeenCalledTimes(1)
    view.rerender(
      <Chat
        messages={[]}
        streaming={false}
        cancelling={false}
        closed={false}
        reconnecting={true}
        interrupted={false}
        error={null}
        suggestions={[]}
        documents={[SPEC]}
        sessionDocuments={[]}
        sessionId="s1"
        onSend={() => {}}
        onCancel={() => {}}
        onReconnect={onReconnect}
        onCreateSkill={() => {}}
        buildingSkill={false}
        proposingTracks={false}
        editingSkillName={null}
        buildError={null}
        buildErrorIsTimeout={false}
        sessionTimeoutSeconds={60}
        onOpenTimeoutModal={() => {}}
        onDismissBuildError={() => {}}
      />,
    )
    view.rerender(
      <Chat
        messages={[]}
        streaming={false}
        cancelling={false}
        closed={false}
        reconnecting={false}
        interrupted={false}
        error={null}
        suggestions={[]}
        documents={[SPEC]}
        sessionDocuments={[]}
        sessionId="s1"
        onSend={() => {}}
        onCancel={() => {}}
        onReconnect={onReconnect}
        onCreateSkill={() => {}}
        buildingSkill={false}
        proposingTracks={false}
        editingSkillName={null}
        buildError={null}
        buildErrorIsTimeout={false}
        sessionTimeoutSeconds={60}
        onOpenTimeoutModal={() => {}}
        onDismissBuildError={() => {}}
      />,
    )
    expect(document.activeElement).toBe(
      screen.getByPlaceholderText('Сообщение планировщику…'),
    )
  })
})
