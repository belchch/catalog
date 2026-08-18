import {
  parseStepsArtifact,
  type ScriptDryRunStage,
  type ScriptDryRunStatus,
  type ScriptTryResult,
  type SessionArtifact,
  type SkillKind,
} from '../api.ts'

export type DryRunState = 'none' | 'ok' | 'error' | 'stale'

export interface ScriptDryRunView {
  status: ScriptDryRunStatus | null
  artifactUpdatedAt: string | undefined
}

const LINE_RE = /\(line (\d+):/
const LINE_SOURCE_RE = /\(line \d+: (.*)\)\s*$/
const STEP_SLOT_RE = /^steps:(\d+)$/

function metaKind(artifacts: SessionArtifact[]): SkillKind | null {
  const meta = artifacts.find((item) => item.type === 'meta')
  if (!meta?.content.trim()) return null
  try {
    const parsed = JSON.parse(meta.content) as { kind?: unknown }
    if (parsed.kind === 'script' || parsed.kind === 'pipeline' || parsed.kind === 'agent') {
      return parsed.kind
    }
    return 'agent'
  } catch {
    return null
  }
}

export function scriptDryRun(artifacts: SessionArtifact[]): ScriptDryRunStatus | null {
  const art = artifacts.find((item) => item.type === 'script')
  if (!art) return null
  const payload = art.dry_run
  if (!payload || Array.isArray(payload)) return null
  return payload
}

export function scriptDryRunView(artifacts: SessionArtifact[]): ScriptDryRunView {
  const art = artifacts.find((item) => item.type === 'script')
  return {
    status: scriptDryRun(artifacts),
    artifactUpdatedAt: art?.updated_at,
  }
}

export function dryRunState(input: {
  status: ScriptDryRunStatus | null | undefined
  artifactUpdatedAt?: string
  dirty?: boolean
}): DryRunState {
  if (input.dirty) return 'stale'
  const status = input.status
  if (status == null || status.time == null) return 'none'
  if (status.ok) return 'ok'
  const updated = input.artifactUpdatedAt ? Date.parse(input.artifactUpdatedAt) : Number.NaN
  const ranAt = Date.parse(status.time)
  if (!Number.isNaN(updated) && !Number.isNaN(ranAt) && updated > ranAt + 1000) {
    return 'stale'
  }
  return 'error'
}

export function dryRunLabel(state: DryRunState): string {
  if (state === 'none') return 'Не прогонялся'
  if (state === 'ok') return 'Прогон ok'
  if (state === 'error') return 'Ошибка'
  return 'Устарел'
}

export function dryRunSummaryLabel(state: DryRunState): string {
  if (state === 'none') return 'Нужен прогон'
  if (state === 'ok') return 'Прогон ok'
  if (state === 'error') return 'Ошибка прогона'
  return 'Прогон устарел'
}

export function dryRunTitle(state: DryRunState): string {
  if (state === 'none') return 'прогон нужен для сборки'
  if (state === 'ok') return 'Прогон ok'
  if (state === 'error') return 'Ошибка прогона'
  return 'код менялся после прогона — прогоните снова'
}

export function dryRunBadgeClass(state: DryRunState): string {
  if (state === 'none') return 'badge-neutral'
  if (state === 'ok') return 'badge-success'
  if (state === 'error') return 'badge-danger'
  return 'badge-warning'
}

export function stageLabel(stage: ScriptDryRunStage | string | null | undefined): string {
  if (stage === 'validate') return 'проверка кода'
  if (stage === 'run') return 'запуск'
  if (stage === 'verify') return 'проверки результата'
  return ''
}

export function errorLineNo(
  status: ScriptDryRunStatus | null | undefined,
  lastRun?: Pick<ScriptTryResult, 'line_no' | 'error'> | null,
): number | null {
  if (lastRun?.line_no != null && lastRun.line_no > 0) return lastRun.line_no
  const text = lastRun?.error ?? status?.error
  if (!text) return null
  const match = text.match(LINE_RE)
  if (!match) return null
  const n = Number(match[1])
  return Number.isFinite(n) && n > 0 ? n : null
}

export function errorSourceLine(
  status: ScriptDryRunStatus | null | undefined,
  lastRun?: Pick<ScriptTryResult, 'source_line' | 'error'> | null,
): string | null {
  if (lastRun?.source_line) return lastRun.source_line
  const text = lastRun?.error ?? status?.error
  if (!text) return null
  const match = text.match(LINE_SOURCE_RE)
  return match?.[1] ?? null
}

function stepLabel(slot: string): string {
  const match = slot.match(STEP_SLOT_RE)
  if (!match) return slot
  return `шаг ${Number(match[1]) + 1}`
}

export function buildBlockReason(artifacts: SessionArtifact[]): string | null {
  const kind = metaKind(artifacts)
  if (kind === null || kind === 'agent') return null

  if (kind === 'script') {
    const view = scriptDryRunView(artifacts)
    const state = dryRunState({
      status: view.status,
      artifactUpdatedAt: view.artifactUpdatedAt,
    })
    if (state === 'ok') return null
    if (state === 'none') {
      return 'Сборка заблокирована: скрипт не прогнан — откройте черновик и нажмите «Прогнать».'
    }
    if (state === 'stale') {
      return 'Сборка заблокирована: прогон устарел — код менялся после прогона.'
    }
    const stage = stageLabel(view.status?.stage)
    if (stage) return `Сборка заблокирована: последний прогон упал (${stage}).`
    return 'Сборка заблокирована: последний прогон упал.'
  }

  const stepsArt = artifacts.find((item) => item.type === 'steps')
  const payload = stepsArt?.dry_run
  if (!Array.isArray(payload) || payload.length === 0) return null
  if (parseStepsArtifact(stepsArt?.content ?? '').parseError) return null

  const blocked = payload.filter((item) => {
    const state = dryRunState({
      status: item,
      artifactUpdatedAt: stepsArt?.updated_at,
    })
    return state !== 'ok'
  })
  if (blocked.length === 0) return null
  return `Сборка заблокирована: script-шаги без зелёного прогона: ${blocked.map((item) => stepLabel(item.slot)).join(', ')}.`
}
