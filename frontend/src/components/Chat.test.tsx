import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DocumentOut } from '../api.ts'
import type { PlannerMessage } from '../hooks/usePlannerSession.ts'
import { Chat } from './Chat.tsx'

const DOC_A: DocumentOut = {
  id: 'doc-a',
  title: 'Устав',
  kind: 'file',
  created_at: '2026-01-01T00:00:00Z',
}

const DOC_B: DocumentOut = {
  id: 'doc-b',
  title: 'ТЗ',
  kind: 'file',
  created_at: '2026-01-01T00:00:00Z',
}

function renderChat(
  overrides: Partial<ComponentProps<typeof Chat>> = {},
) {
  const onSend = vi.fn()
  render(
    <Chat
      messages={[]}
      streaming={false}
      cancelling={false}
      closed={false}
      reconnecting={false}
      error={null}
      suggestions={[]}
      documents={[DOC_A, DOC_B]}
      sessionDocuments={[]}
      sessionId={null}
      onCancel={() => {}}
      onReconnect={() => {}}
      onCreateSkill={() => {}}
      buildingSkill={false}
      proposingTracks={false}
      editingSkillName={null}
      buildError={null}
      buildErrorIsTimeout={false}
      sessionTimeoutSeconds={120}
      onOpenTimeoutModal={() => {}}
      onDismissBuildError={() => {}}
      {...overrides}
      onSend={onSend}
    />,
  )
  return { onSend }
}

function selectDocuments(...titles: string[]) {
  fireEvent.click(screen.getByRole('button', { name: 'Добавить документ' }))
  fireEvent.click(
    screen.getByRole('combobox', { name: 'Добавить документы в сессию' }),
  )
  for (const title of titles) {
    const option = screen.getByRole('option', { name: title })
    const checkbox = option.querySelector('input[type="checkbox"]')
    if (!(checkbox instanceof HTMLInputElement)) {
      throw new Error(`no checkbox for ${title}`)
    }
    fireEvent.click(checkbox)
  }
}

afterEach(cleanup)

describe('Chat suggestion send', () => {
  it('sends selected documents with a starter suggestion, then none after clear', () => {
    const { onSend } = renderChat()
    selectDocuments('Устав', 'ТЗ')

    fireEvent.click(
      screen.getByRole('button', { name: 'Изучи доступные документы' }),
    )

    expect(onSend).toHaveBeenCalledTimes(1)
    expect(onSend).toHaveBeenCalledWith(
      'Изучи доступные документы',
      ['doc-a', 'doc-b'],
      [DOC_A, DOC_B],
    )

    fireEvent.click(
      screen.getByRole('button', { name: 'Изучи доступные документы' }),
    )

    expect(onSend).toHaveBeenCalledTimes(2)
    expect(onSend).toHaveBeenNthCalledWith(
      2,
      'Изучи доступные документы',
      undefined,
      undefined,
    )
  })

  it('sends the suggestion text and drops a typed draft', () => {
    const { onSend } = renderChat()
    fireEvent.change(screen.getByPlaceholderText('Сообщение планировщику…'), {
      target: { value: 'черновик' },
    })

    fireEvent.click(
      screen.getByRole('button', { name: 'Опиши задачу для скилла' }),
    )

    expect(onSend).toHaveBeenCalledWith(
      'Опиши задачу для скилла',
      undefined,
      undefined,
    )
    expect(
      (screen.getByPlaceholderText('Сообщение планировщику…') as HTMLTextAreaElement)
        .value,
    ).toBe('')
  })

  it('keeps composer documents when repeating a message', () => {
    const messages: PlannerMessage[] = [
      { role: 'user', content: 'Старое сообщение' },
    ]
    const { onSend } = renderChat({ messages })
    selectDocuments('Устав')

    expect(screen.getByText('· к отправке', { exact: false })).toBeTruthy()

    fireEvent.click(
      screen.getByRole('button', { name: 'Переотправить это сообщение' }),
    )

    expect(onSend).toHaveBeenCalledTimes(1)
    expect(onSend).toHaveBeenCalledWith('Старое сообщение')
    expect(screen.getByText('· к отправке', { exact: false })).toBeTruthy()
    expect(
      (screen.getByPlaceholderText('Сообщение планировщику…') as HTMLTextAreaElement)
        .value,
    ).toBe('')
  })

  it('still attaches selected documents on Отправить', () => {
    const { onSend } = renderChat()
    selectDocuments('Устав')
    fireEvent.change(screen.getByPlaceholderText('Сообщение планировщику…'), {
      target: { value: 'разбери устав' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }))

    expect(onSend).toHaveBeenCalledWith('разбери устав', ['doc-a'], [DOC_A])
  })
})
