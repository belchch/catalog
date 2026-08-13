import type { ModelOut, ProviderOut } from '../api.ts'
import { ModelCombobox } from './ModelCombobox.tsx'

interface ModelSelectorProps {
  provider: string
  model: string
  providers: ProviderOut[]
  models: ModelOut[]
  loading: boolean
  modelsLoading?: boolean
  onProviderChange: (provider: string) => void
  onModelChange: (model: string) => void
}

export function ModelSelector({
  provider,
  model,
  providers,
  models,
  loading,
  modelsLoading = false,
  onProviderChange,
  onModelChange,
}: ModelSelectorProps) {
  const selectCls = 'field'
  const modelTriggerCls = 'field flex w-full items-center justify-between text-left'
  const modelsBusy = loading || modelsLoading
  return (
    <div className="flex items-center gap-2">
      {loading && (
        <span role="status" aria-live="polite" className="text-[11px] text-ink-faint">
          загрузка…
        </span>
      )}
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
      <div className="flex min-w-[12rem] max-w-[18rem] items-center gap-2">
        {modelsLoading && (
          <span role="status" aria-live="polite" className="shrink-0 text-[11px] text-ink-faint">
            загрузка…
          </span>
        )}
        <div className="min-w-0 flex-1">
          <ModelCombobox
            models={models}
            value={model}
            onChange={onModelChange}
            disabled={modelsBusy || models.length === 0}
            busy={modelsBusy}
            ariaLabel="Модель"
            triggerClassName={modelTriggerCls}
          />
        </div>
      </div>
    </div>
  )
}
