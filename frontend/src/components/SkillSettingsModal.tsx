import { useEffect, useId, useMemo, useState } from 'react'
import {
  configureSkill,
  extractApiDetail,
  listModels,
  listProviders,
  MAX_SKILL_OUTPUTS,
  outputsPayload,
  validateOutputs,
  type ModelOut,
  type OutputDraft,
  type OutputRowError,
  type ProviderOut,
  type SkillOutputOut,
  type SkillPreview,
} from '../api.ts'
import { ModelCombobox } from './ModelCombobox.tsx'
import { OutputsList } from './OutputsList.tsx'

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

function initialOutputs(value: SkillOutputOut[] | undefined): OutputDraft[] {
  return (value ?? []).map((o) => ({
    key: o.key,
    description: o.description,
    multiple: o.multiple === true,
  }))
}

function mergeRowErrors(
  client: (OutputRowError | null)[],
  server: (OutputRowError | null)[],
): (OutputRowError | null)[] {
  return client.map((c, i) => {
    const s = server[i]
    const row: OutputRowError = {
      key: c?.key ?? s?.key,
      description: c?.description ?? s?.description,
      multiple: c?.multiple ?? s?.multiple,
    }
    return row.key || row.description || row.multiple ? row : null
  })
}

// CATALOG-155: formulations mirror `validateOutputs` (api.ts) so a 422 from
// the backend never reads differently than the client's own validation.
const OUTPUTS_KEY_ERROR = 'ключ: только a-z, цифры и _'
const OUTPUTS_KEY_DUPLICATE_ERROR = 'такой ключ уже есть'
const OUTPUTS_DESCRIPTION_ERROR = 'описание не может быть пустым'
const OUTPUTS_MULTIPLE_ERROR = 'несколько документов: только true или false'
const OUTPUTS_ALL_ADDRESSED_ERROR =
  'Бэкенд не принял выходы — поправьте отмеченные строки.'

/** Splits a configure-endpoint 422 detail into per-row output errors and a
 * remaining unaddressed message (CATALOG-155). Segments are separated by
 * `; ` (pydantic's joined ValueError); each is stripped of the `Value
 * error, ` prefix before matching. */
function parseOutputsApiError(
  detail: string,
  outputs: OutputDraft[],
): { rowErrors: (OutputRowError | null)[]; error: string | null } {
  const rowErrors: (OutputRowError | null)[] = outputs.map(() => null)
  const unaddressed: string[] = []
  let addressedAny = false
  const segments = detail.split('; ').map((s) => s.replace(/^Value error,\s*/, ''))
  for (const segment of segments) {
    if (!segment.trim()) continue
    let m = segment.match(/^outputs\[(\d+)\]\.key\b/)
    if (m) {
      const i = Number(m[1])
      if (i >= 0 && i < outputs.length) {
        rowErrors[i] = { ...rowErrors[i], key: OUTPUTS_KEY_ERROR }
        addressedAny = true
      } else {
        unaddressed.push(segment)
      }
      continue
    }
    m = segment.match(/^duplicate output key: '([^']*)'/)
    if (m) {
      const key = m[1]
      const i = outputs.findIndex((o) => o.key.trim() === key)
      if (i >= 0) {
        rowErrors[i] = { ...rowErrors[i], key: OUTPUTS_KEY_DUPLICATE_ERROR }
        addressedAny = true
      } else {
        unaddressed.push(segment)
      }
      continue
    }
    m = segment.match(/^outputs\[(\d+)\]\.description\b/)
    if (m) {
      const i = Number(m[1])
      if (i >= 0 && i < outputs.length) {
        rowErrors[i] = { ...rowErrors[i], description: OUTPUTS_DESCRIPTION_ERROR }
        addressedAny = true
      } else {
        unaddressed.push(segment)
      }
      continue
    }
    m = segment.match(/^outputs\[(\d+)\]\.multiple\b/)
    if (m) {
      const i = Number(m[1])
      if (i >= 0 && i < outputs.length) {
        rowErrors[i] = { ...rowErrors[i], multiple: OUTPUTS_MULTIPLE_ERROR }
        addressedAny = true
      } else {
        unaddressed.push(segment)
      }
      continue
    }
    unaddressed.push(segment)
  }
  const error =
    unaddressed.length > 0
      ? unaddressed.join('; ')
      : addressedAny
        ? OUTPUTS_ALL_ADDRESSED_ERROR
        : null
  return { rowErrors, error }
}

export function SkillSettingsModal({
  skillId,
  preview,
  defaultProvider,
  defaultModel,
  onSave,
  onClose,
}: SkillSettingsModalProps) {
  const titleId = useId()
  const outputsLabelId = useId()
  const outputsHintId = useId()
  const [models, setModels] = useState<ModelOut[]>([])
  const [providers, setProviders] = useState<ProviderOut[]>([])
  const [name, setName] = useState(preview.name)
  const [inputArity, setInputArity] = useState<InputArity>(() => initialArity(preview.input_arity))
  const [outputs, setOutputs] = useState<OutputDraft[]>(() => initialOutputs(preview.outputs))
  const [serverRowErrors, setServerRowErrors] = useState<(OutputRowError | null)[]>([])
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

  const clientOutputsValidation = useMemo(() => validateOutputs(outputs), [outputs])
  const outputsOverLimit = outputs.length > MAX_SKILL_OUTPUTS
  const outputsInvalid = !clientOutputsValidation.ok || outputsOverLimit
  const mergedOutputRowErrors = useMemo(
    () => mergeRowErrors(clientOutputsValidation.rowErrors, serverRowErrors),
    [clientOutputsValidation.rowErrors, serverRowErrors],
  )
  const outputsHint =
    outputs.length === 0
      ? 'Выходов нет — прогон даёт один документ.'
      : 'Первый в списке — основной результат прогона.'

  const handleOutputsChange = (next: OutputDraft[]) => {
    setOutputs(next)
    setServerRowErrors([])
  }

  const saveTitle = nameInvalid
    ? 'Имя не может быть пустым'
    : outputsInvalid
      ? 'Поправьте выходы'
      : undefined

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    setServerRowErrors([])
    try {
      await configureSkill(skillId, {
        model,
        provider,
        reasoning,
        input_arity: inputArity,
        name: name.trim(),
        outputs: outputsPayload(outputs),
      })
      await onSave()
      onClose()
    } catch (e) {
      const detail = extractApiDetail(e)
      const parsed = parseOutputsApiError(detail, outputs)
      setServerRowErrors(parsed.rowErrors)
      setError(parsed.error)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="modal-card flex max-h-[80vh] max-w-md flex-col"
      >
        <div className="mb-3 flex shrink-0 items-center justify-between">
          <h2 id={titleId} className="text-sm font-semibold text-ink">
            Настройка скила
          </h2>
          <button
            type="button"
            className="btn-ghost px-1"
            onClick={onClose}
            disabled={saving}
            aria-label="Закрыть"
          >
            ✕
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto pr-1">
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

          <div className="mb-2">
            <div id={outputsLabelId} className="mb-1 text-[11px] text-ink-faint">
              Выход
            </div>
            <p id={outputsHintId} className="mb-1 text-[10px] text-ink-faint">
              {outputsHint}
            </p>
            <div role="group" aria-labelledby={outputsLabelId} aria-describedby={outputsHintId}>
              <OutputsList
                value={outputs}
                onChange={handleOutputsChange}
                disabled={saving}
                rowErrors={mergedOutputRowErrors}
              />
            </div>
            {outputsOverLimit && (
              <p className="mt-1 text-[11px] text-danger-ink">максимум 8 выходов</p>
            )}
            {outputsInvalid && (
              <p className="mt-1 text-[10px] text-danger-ink">
                Поправьте выходы — иначе не сохранить.
              </p>
            )}
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
        </div>

        <div className="shrink-0 pt-3">
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
              disabled={saving || nameInvalid || outputsInvalid}
              title={saveTitle}
            >
              {saving ? 'Сохранение…' : 'Сохранить'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
