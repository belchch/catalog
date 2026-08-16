import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createCustomCheck,
  hideCustomCheck,
  listCustomChecks,
  listVerifyCheckCatalog,
  previewCustomCheck,
  type CustomCheckOut,
  type VerifyChecksCatalog,
} from '../api.ts'
import { VerifyChecksPicker } from './VerifyChecksPicker.tsx'

vi.mock('../api.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api.ts')>()
  return {
    ...actual,
    listVerifyCheckCatalog: vi.fn(),
    listCustomChecks: vi.fn(),
    createCustomCheck: vi.fn(),
    previewCustomCheck: vi.fn(),
    hideCustomCheck: vi.fn(),
  }
})

afterEach(() => {
  cleanup()
})

const CATALOG: VerifyChecksCatalog = {
  builtin: [
    'non_empty',
    'min_length',
    'max_length',
    'regex_matches',
    'no_leftover_placeholders',
    'markdown_well_formed',
    'has_section',
    'has_field',
    'table_parses',
  ],
  labels: {
    non_empty: 'Не пустой',
    min_length: 'Минимальная длина',
    max_length: 'Максимальная длина',
    regex_matches: 'Совпадение с regex',
    no_leftover_placeholders: 'Без плейсхолдеров',
    markdown_well_formed: 'Корректный markdown',
    has_section: 'Есть раздел',
    has_field: 'Есть поле',
    table_parses: 'Таблица парсится',
  },
}

const CUSTOM: CustomCheckOut = {
  id: 'abc123',
  name: 'Соответствие ТЗ',
  prompt: 'Результат покрывает требования',
  hidden: false,
  created_at: '2026-01-01T00:00:00Z',
}

beforeEach(() => {
  vi.mocked(listVerifyCheckCatalog).mockResolvedValue(CATALOG)
  vi.mocked(listCustomChecks).mockResolvedValue([CUSTOM])
  vi.mocked(createCustomCheck).mockReset()
  vi.mocked(previewCustomCheck).mockReset()
  vi.mocked(hideCustomCheck).mockReset()
})

async function openPicker() {
  fireEvent.click(screen.getByRole('button', { name: /Проверки:|Выбрать проверки/ }))
  await waitFor(() => {
    expect(screen.getByRole('dialog', { name: 'Проверки результата' })).toBeTruthy()
  })
  await waitFor(() => {
    expect(screen.getByText('Стандартные')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Готово' }) as HTMLButtonElement).disabled).toBe(
      false,
    )
  })
}

describe('VerifyChecksPicker', () => {
  it('renders sections and toggles a standard check', async () => {
    const onChange = vi.fn()
    render(<VerifyChecksPicker value={[]} onChange={onChange} />)
    expect(screen.getByText('Проверки результата')).toBeTruthy()
    expect(screen.getByText('Проверки не выбраны')).toBeTruthy()
    await openPicker()
    expect(screen.getByText('Мои проверки')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Новая проверка' })).toBeTruthy()
    const row = screen.getByRole('checkbox', { name: 'Не пустой (non_empty)' })
    expect(row.className).toContain('px-2')
    expect(row.className).toContain('py-1.5')
    expect(row.getAttribute('aria-checked')).toBe('false')
    fireEvent.click(row)
    expect(row.getAttribute('aria-checked')).toBe('true')
    fireEvent.click(screen.getByRole('button', { name: 'Готово' }))
    expect(onChange).toHaveBeenCalledWith([{ check: 'non_empty' }])
  })

  it('blocks Done until a required param is filled', async () => {
    const onChange = vi.fn()
    render(<VerifyChecksPicker value={[]} onChange={onChange} />)
    await openPicker()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Есть раздел (has_section)' }))
    const heading = screen.getByRole('textbox', { name: 'heading' }) as HTMLInputElement
    expect(heading.placeholder).toBe('heading')
    expect(screen.getByText('Заполните параметр')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Готово' }) as HTMLButtonElement).disabled).toBe(
      true,
    )
    fireEvent.change(heading, { target: { value: 'Тезисы' } })
    expect(screen.queryByText('Заполните параметр')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Готово' }))
    expect(onChange).toHaveBeenCalledWith([
      { check: 'has_section', params: { heading: 'Тезисы' } },
    ])
  })

  it('shows a preview verdict on the create form', async () => {
    vi.mocked(previewCustomCheck).mockResolvedValue({
      passed: false,
      failures: ['нет опыта Python'],
    })
    render(<VerifyChecksPicker value={[]} onChange={() => {}} />)
    await openPicker()
    fireEvent.click(screen.getByRole('button', { name: 'Новая проверка' }))
    expect(screen.getByRole('dialog', { name: 'Новая проверка' })).toBeTruthy()
    fireEvent.change(screen.getByRole('textbox', { name: 'Утверждение' }), {
      target: { value: 'Есть опыт Python' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Пример результата' }), {
      target: { value: 'Резюме без стека' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Прогнать на примере' }))
    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toBe('FAIL — нет опыта Python')
    })
  })

  it('does not apply draft changes on Cancel', async () => {
    const onChange = vi.fn()
    render(<VerifyChecksPicker value={[{ check: 'non_empty' }]} onChange={onChange} />)
    await waitFor(() => {
      expect(screen.getByText('Не пустой')).toBeTruthy()
    })
    await openPicker()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Не пустой (non_empty)' }))
    fireEvent.click(screen.getByRole('button', { name: 'Отмена' }))
    expect(onChange).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('keeps my checks visible when hide fails', async () => {
    vi.mocked(hideCustomCheck).mockRejectedValue(new Error('не удалось скрыть'))
    render(<VerifyChecksPicker value={[]} onChange={() => {}} />)
    await openPicker()
    fireEvent.click(screen.getByRole('button', { name: 'Скрыть' }))
    fireEvent.click(screen.getByRole('button', { name: 'Скрыть' }))
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('не удалось скрыть')
    })
    expect(screen.getByText('Соответствие ТЗ')).toBeTruthy()
    expect(screen.getByRole('checkbox', { name: 'Соответствие ТЗ (custom:abc123)' })).toBeTruthy()
  })

  it('focuses New check when both catalogs fail', async () => {
    vi.mocked(listVerifyCheckCatalog).mockRejectedValue(new Error('catalog down'))
    vi.mocked(listCustomChecks).mockRejectedValue(new Error('no workspace'))
    render(<VerifyChecksPicker value={[]} onChange={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Выбрать проверки' }))
    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: 'Проверки результата' })).toBeTruthy()
    })
    await waitFor(() => {
      expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Новая проверка' }))
    })
  })
})
