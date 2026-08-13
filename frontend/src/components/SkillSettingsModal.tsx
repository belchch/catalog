import { useEffect, useMemo, useState } from 'react'
import {
  configureSkill,
  listModels,
  listProviders,
  type ModelOut,
  type ProviderOut,
  type SkillPreview,
} from '../api.ts'
import { ModelCombobox } from './ModelCombobox.tsx'

interface SkillSettingsModalProps {
  skillId: string
  preview: SkillPreview
  defaultProvider: string
  defaultModel: string
  onSave: () => Promise<void>
  onClose: () => void
}

type InputArity = 1 | 2 | null

function initialArity(value: number | null | undefined): InputArity {
  if (value === 1 || value === 2 || value === null) return value
  return 1
}

const ARITY_OPTIONS: { value: InputArity; label: string }[] = [
  { value: 1, label: '1 документ' },
  { value: 2, label: '2 документа' },
  { value: null, label: 'Список' },
]

export function SkillSettingsModal({
  skillId,
  preview,
  defaultProvider,
  defaultModel,
  onSave,
  onClose,
}: SkillSettingsModalProps) {
  const [models, setModels] = useState<ModelOut[]>([])
  const [providers, setProviders] = useState<ProviderOut[]>([])
  const [name, setName] = useState(preview.name)
  const [inputArity, setInputArity] = useState<InputArity>(() => initialArity(preview.input_arity))
  const [model, setModel] = useState(preview.model || defaultModel)
  const [provider, setProvider] = useState(preview.provider || defaultProvider)
  const [reasoning, setReasoning] = useState(preview.reasoning)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const nameInvalid = name.trim().length === 0

  useEffect(() => {
    void (async () => {
      try {
        const [m, p] = await Promise.all([listModels(), listProviders()])
        setModels(m)
        setProviders(p)
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      }
    })()
  }, [])

  const selectedModel = useMemo(
    () => models.find((m) => m.id === model),
    [models, model],
  )
  const reasoningVariants = selectedModel?.reasoning_variants ?? []

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      await configureSkill(skillId, {
        model,
        provider,
        reasoning,
        input_arity: inputArity,
        name: name.trim(),
      })
      await onSave()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-card max-w-md">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink">Настройка скила</h2>
          <button
            type="button"
            className="btn-ghost px-1"
            onClick={onClose}
            disabled={saving}
          >
            ✕
          </button>
        </div>
        <label className="mb-2 block text-[11px] text-ink-faint">
          Имя
          <input
            type="text"
            className="field mt-1"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={saving}
          />
          {nameInvalid && (
            <span className="mt-1 block text-[10px] text-danger-ink">Имя не может быть пустым</span>
          )}
        </label>

        <div className="mb-2">
          <div className="mb-1 text-[11px] text-ink-faint">Вход</div>
          <div
            role="radiogroup"
            aria-label="Вход"
            className="flex flex-wrap gap-1"
            onKeyDown={(e) => {
              const idx = ARITY_OPTIONS.findIndex((o) => o.value === inputArity)
              if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
                e.preventDefault()
                setInputArity(ARITY_OPTIONS[(idx + 1) % ARITY_OPTIONS.length].value)
              } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
                e.preventDefault()
                setInputArity(
                  ARITY_OPTIONS[(idx - 1 + ARITY_OPTIONS.length) % ARITY_OPTIONS.length].value,
                )
              }
            }}
          >
            {ARITY_OPTIONS.map((opt) => {
              const active = inputArity === opt.value
              return (
                <button
                  key={String(opt.value)}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  tabIndex={active ? 0 : -1}
                  className={
                    'rounded px-2 py-1 text-[11px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand ' +
                    (active
                      ? 'bg-brand text-white'
                      : 'bg-surface-muted text-ink-muted hover:bg-surface-hover')
                  }
                  onClick={() => setInputArity(opt.value)}
                >
                  {opt.label}
                </button>
              )
            })}
          </div>
        </div>

        <label className="mb-2 block text-[11px] text-ink-faint">
          Провайдер
          <select
            className="field mt-1"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
          >
            {providers.length === 0 && <option value="">(по умолчанию)</option>}
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
                {p.active ? ' (активный)' : ''}
              </option>
            ))}
          </select>
        </label>

        <div className="mb-2">
          <div className="mb-1 text-[11px] text-ink-faint">Модель</div>
          <ModelCombobox
            models={models}
            value={model}
            onChange={(id) => {
              setModel(id)
              setReasoning('')
            }}
            disabled={models.length === 0}
            ariaLabel="Модель"
            triggerClassName="field flex w-full items-center justify-between text-left"
          />
        </div>

        <label className="mb-4 block text-[11px] text-ink-faint">
          Режим рассуждений
          <select
            className="field mt-1"
            value={reasoning}
            onChange={(e) => setReasoning(e.target.value)}
            disabled={reasoningVariants.length === 0}
          >
            <option value="">(по умолчанию)</option>
            {reasoningVariants.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
          {reasoningVariants.length === 0 && (
            <span className="mt-1 block text-[10px] text-ink-faint">
              модель не поддерживает явный режим рассуждений
            </span>
          )}
        </label>

        {error && <p className="mb-2 text-xs text-danger-ink">{error}</p>}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="btn-secondary"
            onClick={onClose}
            disabled={saving}
          >
            Отмена
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={() => void handleSave()}
            disabled={saving || nameInvalid}
          >
            {saving ? 'Сохранение…' : 'Сохранить'}
          </button>
        </div>
      </div>
    </div>
  )
}
