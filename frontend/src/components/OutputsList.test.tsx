import { useState } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MAX_SKILL_OUTPUTS, type OutputDraft } from '../api.ts'
import { OutputsList } from './OutputsList.tsx'

afterEach(() => {
  cleanup()
})

function Harness({ initial }: { initial: OutputDraft[] }) {
  const [value, setValue] = useState<OutputDraft[]>(initial)
  return <OutputsList value={value} onChange={setValue} />
}

function row(key: string, description = ''): OutputDraft {
  return { key, description }
}

describe('OutputsList — key input does not lose focus (CATALOG-157)', () => {
  it('keeps focus in the "ключ" input across multiple typed characters', () => {
    // CATALOG-157: до фикса React-key строки зависел от row.key, поэтому ввод
    // символа перемонтировал строку и input терял фокус. `fireEvent.change` этот
    // баг НЕ ловит — он не зависит от фокуса и просто задаёт value напрямую.
    // Поэтому здесь мы явно фокусируем input и после КАЖДОГО символа проверяем
    // document.activeElement — второй символ уже проваливался бы без фикса.
    render(<Harness initial={[row('')]} />)
    const input = screen.getByLabelText('ключ') as HTMLInputElement
    input.focus()
    expect(document.activeElement).toBe(input)

    const chars = ['t', 'a', 'b', 'l', 'e']
    let current = ''
    for (const ch of chars) {
      current += ch
      fireEvent.change(input, { target: { value: current } })
      expect(document.activeElement).toBe(input)
    }

    expect(input.value).toBe('table')
  })
})

describe('OutputsList — reorder, remove, add, limit', () => {
  it('moves values with the row on ↑ / ↓ (no swap between rows)', () => {
    render(<Harness initial={[row('brief', 'Резюме'), row('table', 'Таблица')]} />)
    fireEvent.click(screen.getByRole('button', { name: 'Поднять выход table' }))
    const keys = screen.getAllByLabelText('ключ') as HTMLInputElement[]
    expect(keys.map((el) => el.value)).toEqual(['table', 'brief'])
    const descs = screen.getAllByLabelText('описание') as HTMLInputElement[]
    expect(descs.map((el) => el.value)).toEqual(['Таблица', 'Резюме'])
  })

  it('removes exactly the targeted row', () => {
    render(
      <Harness
        initial={[row('brief', 'Резюме'), row('table', 'Таблица'), row('list', 'Список')]}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Удалить выход table' }))
    const keys = screen.getAllByLabelText('ключ') as HTMLInputElement[]
    expect(keys.map((el) => el.value)).toEqual(['brief', 'list'])
  })

  it('adds a row and focuses its "ключ" input', () => {
    render(<Harness initial={[]} />)
    fireEvent.click(screen.getByRole('button', { name: 'Добавить выход' }))
    const input = screen.getByLabelText('ключ') as HTMLInputElement
    expect(document.activeElement).toBe(input)
  })

  it('disables "Добавить выход" once MAX_SKILL_OUTPUTS is reached', () => {
    const initial = Array.from({ length: MAX_SKILL_OUTPUTS }, (_, i) => row(`k${i}`))
    render(<Harness initial={initial} />)
    const btn = screen.getByRole('button', { name: 'Добавить выход' }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    expect(btn.title).toBe('максимум 8 выходов')
  })

  it('focuses first key ref via firstKeyRef prop', () => {
    const onChange = vi.fn()
    let ref: HTMLInputElement | null = null
    render(
      <OutputsList
        value={[row('brief'), row('table')]}
        onChange={onChange}
        firstKeyRef={(el) => {
          ref = el
        }}
      />,
    )
    expect(ref).toBe(screen.getAllByLabelText('ключ')[0])
  })
})
