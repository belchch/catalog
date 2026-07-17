import type { ModelOut, ProviderOut } from '../api.ts'

interface ModelSelectorProps {
  provider: string
  model: string
  providers: ProviderOut[]
  models: ModelOut[]
  loading: boolean
  onProviderChange: (provider: string) => void
  onModelChange: (model: string) => void
}

/**
 * Global model/provider picker shown in the app header (CATALOG-14). Selecting
 * a provider reloads that provider's model list; the active runtime selection
 * is synced to the backend and localStorage by the parent hook.
 */
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
      <select
        className={selectCls}
        value={model}
        onChange={(e) => onModelChange(e.target.value)}
        disabled={loading || models.length === 0}
        aria-label="Модель"
      >
        {models.length === 0 && <option value={model}>{model}</option>}
        {models.map((m) => (
          <option key={m.id} value={m.id}>
            {m.name}
            {m.supports_reasoning ? ' 🧠' : ''}
          </option>
        ))}
      </select>
    </div>
  )
}
