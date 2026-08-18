import {
  parseStepsArtifact,
  type ArtifactType,
  type PipelineStepDraft,
  type SessionArtifact,
} from '../api.ts'
import {
  dryRunBadgeClass,
  dryRunState,
  dryRunSummaryLabel,
  dryRunTitle,
  scriptDryRunView,
} from '../lib/dryRun.ts'

interface ArtifactSummaryCardProps {
  artifacts: SessionArtifact[]
  loading: boolean
  error: string | null
  streaming: boolean
  onOpen: () => void
}

const artifactLabels: Record<ArtifactType, string> = {
  meta: 'Настройки',
  steps: 'Шаги',
  prompt: 'Промпт',
  script: 'Скрипт',
}

const baseTypes: ArtifactType[] = ['meta', 'prompt', 'script']

function formatStepCount(n: number): string {
  const n10 = n % 10
  const n100 = n % 100
  if (n10 === 1 && n100 !== 11) return `${n} шаг`
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return `${n} шага`
  return `${n} шагов`
}

function isRowReady(type: ArtifactType, artifacts: SessionArtifact[]): boolean {
  const art = artifacts.find((item) => item.type === type)
  if (!art) return false
  if (type === 'steps') {
    if (art.is_valid === false) return false
    return parseStepsArtifact(art.content).steps.length >= 1
  }
  return art.content.trim().length > 0
}

function promptRequired(steps: PipelineStepDraft[]): boolean {
  return steps.some((step) => step.type === 'llm' && !step.system_prompt.trim())
}

function scriptRequired(steps: PipelineStepDraft[]): boolean {
  return steps.some((step) => step.type === 'script' && !step.code.trim())
}

export function ArtifactSummaryCard({
  artifacts,
  loading,
  error,
  streaming,
  onOpen,
}: ArtifactSummaryCardProps) {
  const hasSteps = artifacts.some((item) => item.type === 'steps')
  const visible: ArtifactType[] = hasSteps
    ? ['meta', 'steps', 'prompt', 'script']
    : baseTypes
  const stepsArt = artifacts.find((item) => item.type === 'steps')
  const parsedSteps = stepsArt ? parseStepsArtifact(stepsArt.content).steps : []
  const needPrompt = !hasSteps || promptRequired(parsedSteps)
  const needScript = !hasSteps || scriptRequired(parsedSteps)
  const required = visible.filter((type) => {
    if (type === 'prompt') return needPrompt
    if (type === 'script') return needScript
    return true
  })
  const readyCount = required.filter((type) => isRowReady(type, artifacts)).length
  const scriptView = scriptDryRunView(artifacts)
  const scriptRunState = dryRunState({
    status: scriptView.status,
    artifactUpdatedAt: scriptView.artifactUpdatedAt,
  })

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
            ? `Готово ${readyCount} из ${required.length} разделов`
            : 'Артефакты появятся по мере работы с чатом'}
      </p>

      <div className="artifact-summary__group">
        <p className="artifact-summary__label">Содержимое</p>
        <ul className="artifact-summary__list">
          {visible.map((type) => {
            const needed =
              type === 'prompt' ? needPrompt : type === 'script' ? needScript : true
            const ready = needed && isRowReady(type, artifacts)
            return (
              <li key={type}>
                <span className={ready ? 'artifact-status artifact-status--ready' : 'artifact-status'}>
                  {ready ? '✓' : '—'}
                </span>
                <span>{artifactLabels[type]}</span>
                {type === 'steps' && ready && (
                  <span className="artifact-summary__ready">{formatStepCount(parsedSteps.length)}</span>
                )}
                {type === 'script' && ready && (
                  <span
                    className={`${dryRunBadgeClass(scriptRunState)} ml-auto`}
                    title={dryRunTitle(scriptRunState)}
                  >
                    {dryRunSummaryLabel(scriptRunState)}
                  </span>
                )}
                {type !== 'steps' && type !== 'script' && ready && (
                  <span className="artifact-summary__ready">готово</span>
                )}
                {type !== 'steps' && !needed && (
                  <span className="artifact-summary__ready">не требуется</span>
                )}
              </li>
            )
          })}
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
