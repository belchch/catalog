import { useEffect, useMemo, useState } from 'react'
import {
  configureSkill,
  listModels,
  listProviders,
  type ModelOut,
  type ProviderOut,
  type SkillPreview,
} from '../api.ts'

interface SkillSettingsModalProps {
  skillId: string
  preview: SkillPreview
  onSave: () => Promise<void>
  onClose: () => void
}

/**
 * Pre-save settings modal (CATALOG-6): lets the user pick model / provider /
 * reasoning variant before the skill is committed. Options are loaded from the
 * backend (/models, /providers). Reasoning variants come from the selected
 * model's catalog entry.
 */
export function SkillSettingsModal({ skillId, preview, onSave, onClose }: SkillSettingsModalProps) {
  const [models, setModels] = useState<ModelOut[]>([])
  const [providers, setProviders] = useState<ProviderOut[]>([])
  const [model, setModel] = useState(preview.model)
  const [provider, setProvider] = useState(preview.provider)
  const [reasoning, setReasoning] = useState(preview.reasoning)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
      await configureSkill(skillId, { model, provider, reasoning })
      await onSave()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  const fieldCls = 'w-full rounded bg-slate-800 px-2 py-1 text-xs text-slate-100'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-lg border border-slate-700 bg-slate-900 p-4 shadow-xl">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-100">Настройка скила</h2>
          <button
            className="text-xs text-slate-400 hover:text-slate-200"
            onClick={onClose}
            disabled={saving}
          >
            ✕
          </button>
        </div>
        <p className="mb-3 truncate text-xs text-slate-400">{preview.name}</p>

        <label className="mb-2 block text-[11px] text-slate-400">
          Провайдер
          <select
            className={`mt-1 ${fieldCls}`}
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

        <label className="mb-2 block text-[11px] text-slate-400">
          Модель
          <select
            className={`mt-1 ${fieldCls}`}
            value={model}
            onChange={(e) => {
              setModel(e.target.value)
              setReasoning('')
            }}
          >
            {models.length === 0 && <option value={preview.model}>{preview.model}</option>}
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </label>

        <label className="mb-4 block text-[11px] text-slate-400">
          Режим рассуждений
          <select
            className={`mt-1 ${fieldCls}`}
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
            <span className="mt-1 block text-[10px] text-slate-500">
              модель не поддерживает явный режим рассуждений
            </span>
          )}
        </label>

        {error && <p className="mb-2 text-xs text-red-400">{error}</p>}

        <div className="flex justify-end gap-2">
          <button
            className="rounded bg-slate-700 px-3 py-1 text-xs text-slate-200"
            onClick={onClose}
            disabled={saving}
          >
            Отмена
          </button>
          <button
            className="rounded bg-indigo-600 px-3 py-1 text-xs text-white disabled:opacity-50"
            onClick={() => void handleSave()}
            disabled={saving}
          >
            {saving ? 'Сохранение…' : 'Сохранить'}
          </button>
        </div>
      </div>
    </div>
  )
}
