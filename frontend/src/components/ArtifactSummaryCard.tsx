import type { ArtifactType, SessionArtifact } from '../api.ts'

interface ArtifactSummaryCardProps {
  artifacts: SessionArtifact[]
  loading: boolean
  error: string | null
  streaming: boolean
  onOpen: () => void
}

const artifactLabels: Record<ArtifactType, string> = {
  meta: 'Настройки',
  prompt: 'Промпт',
  script: 'Скрипт',
}

const artifactTypes: ArtifactType[] = ['meta', 'prompt', 'script']

/** A quiet, reference-style overview of the generated skill draft. */
export function ArtifactSummaryCard({
  artifacts,
  loading,
  error,
  streaming,
  onOpen,
}: ArtifactSummaryCardProps) {
  const available = new Set(artifacts.filter((item) => item.content.trim()).map((item) => item.type))
  const readyCount = available.size

  return (
    <aside className="artifact-summary" aria-label="Черновик скилла">
      <div className="artifact-summary__header">
        <div>
          <p className="artifact-summary__eyebrow">Черновик</p>
          <h2>Артефакты скилла</h2>
        </div>
        <button type="button" className="icon-button" onClick={onOpen} aria-label="Открыть черновик">
          ↗
        </button>
      </div>

      <p className="artifact-summary__description">
        {streaming
          ? 'Планировщик обновляет черновик…'
          : readyCount > 0
            ? `Готово ${readyCount} из 3 разделов`
            : 'Артефакты появятся по мере работы с чатом'}
      </p>

      <div className="artifact-summary__group">
        <p className="artifact-summary__label">Содержимое</p>
        <ul className="artifact-summary__list">
          {artifactTypes.map((type) => (
            <li key={type}>
              <span className={available.has(type) ? 'artifact-status artifact-status--ready' : 'artifact-status'}>
                {available.has(type) ? '✓' : '—'}
              </span>
              <span>{artifactLabels[type]}</span>
              {available.has(type) && <span className="artifact-summary__ready">готово</span>}
            </li>
          ))}
        </ul>
      </div>

      {error && <p className="artifact-summary__error">{error}</p>}
      {loading && <p className="artifact-summary__muted">Загружаем черновик…</p>}

      <button type="button" className="artifact-summary__open" onClick={onOpen}>
        Открыть черновик
      </button>
    </aside>
  )
}
