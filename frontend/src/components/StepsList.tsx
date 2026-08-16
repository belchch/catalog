import type { PipelineStepDraft, PipelineStepType } from '../api.ts'

const PRE_CLS =
  'mt-1 overflow-auto max-h-40 whitespace-pre-wrap break-words rounded bg-surface-muted p-1.5 font-mono text-[11px] text-ink-muted'

function firstEmptyIndex(
  steps: PipelineStepDraft[],
  type: PipelineStepType,
  field: 'code' | 'system_prompt',
): number {
  return steps.findIndex((step) => step.type === type && !step[field].trim())
}

function orDefault(value: string): string {
  return value.trim() || 'по умолчанию скила'
}

function typeBadge(type: PipelineStepType): { className: string; label: string } {
  if (type === 'script') return { className: 'badge-info', label: 'SCRIPT' }
  if (type === 'llm') return { className: 'badge-accent', label: 'LLM' }
  return { className: 'badge-success', label: 'SKILL' }
}

function shortPin(hash: string): string {
  return hash.length > 8 ? hash.slice(0, 8) : hash
}

function SkillStepDetails({ step }: { step: PipelineStepDraft }) {
  if (step.skill_name.trim()) {
    const kind = step.skill_kind.trim()
    return (
      <>
        <p className="mt-1 text-[11px] text-ink-muted">
          {kind ? `${step.skill_name} · ${kind}` : step.skill_name}
        </p>
        {step.config_hash.trim() ? (
          <p className="mt-1 text-[11px] text-ink-muted">
            пин{' '}
            <span className="font-mono" title={step.config_hash}>
              {shortPin(step.config_hash)}
            </span>
          </p>
        ) : null}
      </>
    )
  }
  if (step.skill_id.trim()) {
    return (
      <>
        <p className="mt-1 break-words font-mono text-[11px] text-ink-muted">
          id: {step.skill_id}
        </p>
        <p className="mt-1 text-[10px] text-ink-faint">
          имя и пин появятся при сборке
        </p>
      </>
    )
  }
  return <p className="mt-1 text-[11px] text-warning-ink">скилл не выбран</p>
}

export function StepsList({ steps }: { steps: PipelineStepDraft[] }) {
  const firstEmptyScript = firstEmptyIndex(steps, 'script', 'code')
  const firstEmptyLlm = firstEmptyIndex(steps, 'llm', 'system_prompt')

  return (
    <ol className="flex flex-col gap-1.5">
      {steps.map((step, index) => {
        const idLabel = step.id.trim() ? step.id : '(без id)'
        const badge = typeBadge(step.type)
        return (
          <li key={step.id || index}>
            <div className="flex flex-wrap items-center gap-2 text-[11px]">
              <span className="font-mono text-ink-faint">[{index + 1}]</span>
              <span
                className={
                  'truncate font-mono ' +
                  (step.id.trim() ? 'text-ink' : 'text-warning-ink')
                }
              >
                {idLabel}
              </span>
              <span className={badge.className}>{badge.label}</span>
              <span className="badge-neutral">
                {step.input === 'documents' ? 'документы' : 'предыдущий'}
              </span>
            </div>
            <details>
              <summary className="cursor-pointer text-[11px] text-ink-faint">
                подробнее
              </summary>
              {step.type === 'script' ? (
                step.code.trim() ? (
                  <pre className={PRE_CLS}>{step.code}</pre>
                ) : index === firstEmptyScript ? (
                  <p className="mt-1 text-[10px] text-ink-faint">
                    код возьмётся из артефакта Script при сборке
                  </p>
                ) : (
                  <p className="mt-1 text-[11px] text-warning-ink">код не задан</p>
                )
              ) : step.type === 'llm' ? (
                <>
                  {step.system_prompt.trim() ? (
                    <pre className={PRE_CLS}>{step.system_prompt}</pre>
                  ) : index === firstEmptyLlm ? (
                    <p className="mt-1 text-[10px] text-ink-faint">
                      промпт возьмётся из артефакта Prompt при сборке
                    </p>
                  ) : (
                    <p className="mt-1 text-[11px] text-warning-ink">промпт не задан</p>
                  )}
                  <p className="mt-1 text-[11px] text-ink-muted">
                    {orDefault(step.model)} / {orDefault(step.provider)} / {orDefault(step.reasoning)}
                  </p>
                  <p className="mt-0.5 text-[11px] text-ink-muted">
                    {step.allowed_tools.length > 0 ? step.allowed_tools.join(', ') : '—'}
                  </p>
                </>
              ) : (
                <SkillStepDetails step={step} />
              )}
            </details>
          </li>
        )
      })}
    </ol>
  )
}
