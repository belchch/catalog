import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  configureSkill,
  listModels,
  listProviders,
  type ModelOut,
  type ProviderOut,
  type SkillBuilt,
  type SkillPreview,
} from '../api.ts'
import { SkillSettingsModal } from './SkillSettingsModal.tsx'

vi.mock('../api.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api.ts')>()
  return {
    ...actual,
    configureSkill: vi.fn(),
    listModels: vi.fn(),
    listProviders: vi.fn(),
  }
})

afterEach(() => {
  cleanup()
})

const MODELS: ModelOut[] = [
  {
    id: 'gpt-5',
    name: 'GPT-5',
    context_length: null,
    supports_reasoning: false,
    reasoning_variants: [],
  },
]

const PROVIDERS: ProviderOut[] = [{ id: 'openrouter', name: 'OpenRouter', active: true }]

function basePreview(overrides: Partial<SkillPreview> = {}): SkillPreview {
  return {
    name: 'Мой скилл',
    description: null,
    kind: 'agent',
    model: 'gpt-5',
    provider: 'openrouter',
    reasoning: '',
    input_arity: 1,
    allowed_tools: [],
    outputs: [],
    ...overrides,
  }
}

function builtFrom(preview: SkillPreview): SkillBuilt {
  return { skill_id: 'skill-1', config: preview }
}

beforeEach(() => {
  vi.mocked(listModels).mockReset().mockResolvedValue(MODELS)
  vi.mocked(listProviders).mockReset().mockResolvedValue(PROVIDERS)
  vi.mocked(configureSkill).mockReset()
})

function renderModal(preview: SkillPreview, extra: { onSave?: () => Promise<void>; onClose?: () => void } = {}) {
  const onSave = extra.onSave ?? vi.fn(async () => {})
  const onClose = extra.onClose ?? vi.fn()
  render(
    <SkillSettingsModal
      skillId="skill-1"
      preview={preview}
      defaultProvider="openrouter"
      defaultModel="gpt-5"
      onSave={onSave}
      onClose={onClose}
    />,
  )
  return { onSave, onClose }
}

async function waitForModelsLoaded() {
  await waitFor(() => expect(listModels).toHaveBeenCalled())
}

describe('SkillSettingsModal outputs block', () => {
  it('shows outputs declared in preview with descriptions and marks the first as primary', async () => {
    const preview = basePreview({
      outputs: [
        { key: 'summary', description: 'Краткое резюме' },
        { key: 'details', description: 'Подробности', multiple: true },
      ],
    })
    renderModal(preview)
    await waitForModelsLoaded()

    expect(screen.getByText('Первый в списке — основной результат прогона.')).toBeTruthy()
    const firstKey = document.getElementById('outputs-key-0') as HTMLInputElement
    const firstDesc = document.getElementById('outputs-desc-0') as HTMLInputElement
    const secondKey = document.getElementById('outputs-key-1') as HTMLInputElement
    expect(firstKey.value).toBe('summary')
    expect(firstDesc.value).toBe('Краткое резюме')
    expect(secondKey.value).toBe('details')
    expect(screen.getAllByText('основной')).toHaveLength(1)
  })

  it('shows the empty-state hint (not an error) and saves an unchanged empty list', async () => {
    const preview = basePreview({ outputs: [] })
    const { onSave, onClose } = renderModal(preview)
    await waitForModelsLoaded()

    expect(screen.getByText('Выходов нет — прогон даёт один документ.')).toBeTruthy()
    const saveButton = screen.getByRole('button', { name: 'Сохранить' }) as HTMLButtonElement
    expect(saveButton.disabled).toBe(false)

    vi.mocked(configureSkill).mockResolvedValue(builtFrom(preview))
    fireEvent.click(saveButton)
    await waitFor(() => expect(configureSkill).toHaveBeenCalledTimes(1))
    expect(configureSkill).toHaveBeenCalledWith(
      'skill-1',
      expect.objectContaining({ outputs: [] }),
    )
    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect(onClose).toHaveBeenCalled()
  })

  it('adds, edits, and removes an output row', async () => {
    const preview = basePreview({ outputs: [] })
    renderModal(preview)
    await waitForModelsLoaded()

    fireEvent.click(screen.getByRole('button', { name: 'Добавить выход' }))
    const keyInput = document.getElementById('outputs-key-0') as HTMLInputElement
    const descInput = document.getElementById('outputs-desc-0') as HTMLInputElement
    fireEvent.change(keyInput, { target: { value: 'summary' } })
    fireEvent.change(descInput, { target: { value: 'Резюме' } })
    expect((document.getElementById('outputs-key-0') as HTMLInputElement).value).toBe('summary')

    fireEvent.click(screen.getByRole('button', { name: 'Удалить выход summary' }))
    expect(document.getElementById('outputs-key-0')).toBeNull()
    expect(screen.getByText('Выходов нет — прогон даёт один документ.')).toBeTruthy()
  })

  it('reordering the first row changes the primary sent to configureSkill', async () => {
    const preview = basePreview({
      outputs: [
        { key: 'summary', description: 'Краткое резюме' },
        { key: 'details', description: 'Подробности' },
      ],
    })
    renderModal(preview)
    await waitForModelsLoaded()

    fireEvent.click(screen.getByRole('button', { name: 'Поднять выход details' }))
    expect((document.getElementById('outputs-key-0') as HTMLInputElement).value).toBe('details')
    expect((document.getElementById('outputs-key-1') as HTMLInputElement).value).toBe('summary')

    vi.mocked(configureSkill).mockResolvedValue(builtFrom(preview))
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(configureSkill).toHaveBeenCalledTimes(1))
    expect(configureSkill).toHaveBeenCalledWith(
      'skill-1',
      expect.objectContaining({
        outputs: [
          { key: 'details', description: 'Подробности' },
          { key: 'summary', description: 'Краткое резюме' },
        ],
      }),
    )
  })

  it('blocks Save and shows a row error on a duplicate key', async () => {
    const preview = basePreview({
      outputs: [
        { key: 'summary', description: 'Первое' },
        { key: 'summary', description: 'Второе' },
      ],
    })
    renderModal(preview)
    await waitForModelsLoaded()

    expect(screen.getByText('такой ключ уже есть')).toBeTruthy()
    const saveButton = screen.getByRole('button', { name: 'Сохранить' }) as HTMLButtonElement
    expect(saveButton.disabled).toBe(true)
    expect(saveButton.getAttribute('title')).toBe('Поправьте выходы')
  })

  it('blocks Save and shows a row error on a malformed key', async () => {
    const preview = basePreview({
      outputs: [{ key: 'Bad Key!', description: 'Текст' }],
    })
    renderModal(preview)
    await waitForModelsLoaded()

    expect(screen.getByText('ключ: только a-z, цифры и _')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Сохранить' }) as HTMLButtonElement).disabled).toBe(
      true,
    )
  })

  it('blocks Save and shows a row error on an empty description', async () => {
    const preview = basePreview({
      outputs: [{ key: 'summary', description: '' }],
    })
    renderModal(preview)
    await waitForModelsLoaded()

    expect(screen.getByText('описание не может быть пустым')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Сохранить' }) as HTMLButtonElement).disabled).toBe(
      true,
    )
  })

  it('blocks Save with a block-level error when more than 8 outputs are declared', async () => {
    const preview = basePreview({
      outputs: Array.from({ length: 9 }, (_, i) => ({
        key: `k${i}`,
        description: `Описание ${i}`,
      })),
    })
    renderModal(preview)
    await waitForModelsLoaded()

    expect(screen.getByText('максимум 8 выходов')).toBeTruthy()
    expect(screen.getByText('Поправьте выходы — иначе не сохранить.')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Сохранить' }) as HTMLButtonElement).disabled).toBe(
      true,
    )
  })

  it('routes an addressed 422 to the matching row and keeps the rest in the error banner', async () => {
    const preview = basePreview({
      outputs: [{ key: 'summary', description: 'Резюме' }],
    })
    renderModal(preview)
    await waitForModelsLoaded()

    vi.mocked(configureSkill).mockRejectedValueOnce(
      new Error(
        JSON.stringify({
          detail: "Value error, outputs[0].description must be non-empty; some other backend issue",
        }),
      ),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => {
      expect(screen.getByText('описание не может быть пустым')).toBeTruthy()
    })
    expect(screen.getByText('some other backend issue')).toBeTruthy()
  })
})
