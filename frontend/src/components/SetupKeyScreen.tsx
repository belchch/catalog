import { useId, useState, type FormEvent } from 'react'
import { extractApiDetail, saveProviderKey, type SetupOut } from '../api.ts'

type ProviderChoice = 'openrouter' | 'zai'

interface SetupKeyScreenProps {
  onConfigured: (setup: SetupOut) => void
}

const PROVIDERS: { id: ProviderChoice; label: string }[] = [
  { id: 'openrouter', label: 'OpenRouter' },
  { id: 'zai', label: 'z.ai' },
]

export function SetupKeyScreen({ onConfigured }: SetupKeyScreenProps) {
  const titleId = useId()
  const keyInputId = useId()
  const [provider, setProvider] = useState<ProviderChoice>('openrouter')
  const [apiKey, setApiKey] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const trimmedKey = apiKey.trim()
  const canSubmit = trimmedKey.length > 0 && !submitting

  const handleProviderChange = (next: ProviderChoice) => {
    setProvider(next)
    setError(null)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    setError(null)
    try {
      const body =
        provider === 'openrouter'
          ? { openrouter_api_key: trimmedKey }
          : { zai_api_key: trimmedKey }
      const result = await saveProviderKey(body)
      onConfigured(result)
    } catch (err) {
      setError(extractApiDetail(err))
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface p-4">
      <div className="modal-card max-w-md space-y-4">
        <div className="flex items-center gap-2">
          <span className="catalog-mark" aria-hidden="true">
            C
          </span>
          <div>
            <h1 id={titleId} className="text-base font-semibold text-ink">
              Настройка Catalog
            </h1>
            <p className="text-xs text-ink-faint">
              Добавьте ключ LLM-провайдера, чтобы начать работу
            </p>
          </div>
        </div>

        <p className="text-xs text-ink-faint">
          Catalog обращается к LLM-провайдеру. Вставьте API-ключ — он сохранится
          локально и не показывается обратно.
        </p>

        <form
          aria-labelledby={titleId}
          aria-busy={submitting}
          className="space-y-4"
          onSubmit={(e) => void handleSubmit(e)}
        >
          <fieldset disabled={submitting} className="space-y-2">
            <legend className="sr-only">Провайдер</legend>
            <div role="radiogroup" aria-label="Провайдер" className="space-y-2">
              {PROVIDERS.map((p) => {
                const selected = provider === p.id
                const radioId = `${titleId}-${p.id}`
                return (
                  <label
                    key={p.id}
                    htmlFor={radioId}
                    className={
                      selected
                        ? 'flex cursor-pointer items-center gap-2 rounded border border-line-brand bg-brand-soft px-3 py-2 focus-within:ring-2 focus-within:ring-brand'
                        : 'flex cursor-pointer items-center gap-2 rounded border border-line bg-surface-muted px-3 py-2 focus-within:ring-2 focus-within:ring-brand'
                    }
                  >
                    <input
                      id={radioId}
                      type="radio"
                      name="provider"
                      value={p.id}
                      checked={selected}
                      onChange={() => handleProviderChange(p.id)}
                    />
                    <span className="text-xs text-ink">{p.label}</span>
                  </label>
                )
              })}
            </div>
          </fieldset>

          <div>
            <label htmlFor={keyInputId} className="sr-only">
              API-ключ
            </label>
            <input
              id={keyInputId}
              type="password"
              className="field"
              placeholder="Вставьте API-ключ"
              autoComplete="off"
              spellCheck={false}
              autoFocus
              value={apiKey}
              disabled={submitting}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </div>

          {error ? (
            <p role="alert" aria-live="assertive" className="text-xs text-danger-ink">
              {error}
            </p>
          ) : null}

          <button type="submit" className="btn-primary w-full" disabled={!canSubmit}>
            {submitting ? 'Сохранение…' : 'Сохранить ключ'}
          </button>
        </form>

        <p className="text-xs text-ink-faint">
          Где взять ключ: OpenRouter —{' '}
          <a
            href="https://openrouter.ai/keys"
            target="_blank"
            rel="noopener noreferrer"
            className="text-brand-ink hover:underline"
          >
            openrouter.ai/keys
          </a>
          , z.ai —{' '}
          <a
            href="https://z.ai"
            target="_blank"
            rel="noopener noreferrer"
            className="text-brand-ink hover:underline"
          >
            z.ai
          </a>
          .
        </p>
      </div>
    </div>
  )
}
