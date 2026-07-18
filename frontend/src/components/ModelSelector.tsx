import type { ModelOut, ProviderOut } from '../api.ts'
import { ModelCombobox } from './ModelCombobox.tsx'

interface ModelSelectorProps {
  provider: string
  model: string
  providers: ProviderOut[]
  models: ModelOut[]
  loading: boolean
  onProviderChange: (provider: string) => void
  onModelChange: (model: string) => void
}

export function ModelSelector({
  provider,
  model,
  providers,
  models,
  loading,
  onProviderChange,
  onModelChange,
}: ModelSelectorProps) {
  const selectCls =
    'rounded bg-slate-800 px-2 py-1 text-xs text-slate-100 disabled:opacity-50'
  const modelTriggerCls =
    'flex w-full items-center justify-between rounded bg-slate-800 px-2 py-1 text-left text-xs text-slate-100 disabled:opacity-50'
  return (
    <div className="flex items-center gap-2">
      {loading && <span className="text-[11px] text-slate-500">загрузка…</span>}
      <select
        className={selectCls}
        value={provider}
        onChange={(e) => onProviderChange(e.target.value)}
        disabled={loading || providers.length === 0}
        aria-label="Провайдер"
      >
        {providers.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
            {p.active ? ' ●' : ''}
          </option>
        ))}
      </select>
      <div className="min-w-[12rem] max-w-[18rem]">
        <ModelCombobox
          models={models}
          value={model}
          onChange={onModelChange}
          disabled={loading || models.length === 0}
          ariaLabel="Модель"
          triggerClassName={modelTriggerCls}
        />
      </div>
    </div>
  )
}
