import { describe, expect, it } from 'vitest'
import type { ScriptDryRunStatus, SessionArtifact } from '../api.ts'
import {
  buildBlockReason,
  dryRunBadgeClass,
  dryRunLabel,
  dryRunState,
  dryRunSummaryLabel,
  errorLineNo,
  errorSourceLine,
  scriptDryRun,
  stageLabel,
} from './dryRun.ts'

function art(
  type: SessionArtifact['type'],
  content: string,
  extra: Partial<SessionArtifact> = {},
): SessionArtifact {
  return {
    type,
    content,
    is_valid: true,
    error: null,
    source: 'llm',
    updated_at: '2026-08-18T10:00:00Z',
    ...extra,
  }
}

function status(extra: Partial<ScriptDryRunStatus> = {}): ScriptDryRunStatus {
  return {
    slot: 'script',
    sha256: 'abc',
    ok: false,
    stage: null,
    error: null,
    time: null,
    ...extra,
  }
}

describe('dryRunState', () => {
  it('maps the four states in rule order', () => {
    expect(
      dryRunState({
        status: status({ ok: true, time: '2026-08-18T09:00:00Z' }),
        dirty: true,
      }),
    ).toBe('stale')
    expect(dryRunState({ status: null })).toBe('none')
    expect(dryRunState({ status: status({ time: null }) })).toBe('none')
    expect(
      dryRunState({
        status: status({ ok: true, time: '2026-08-18T09:00:00Z' }),
        artifactUpdatedAt: '2026-08-18T12:00:00Z',
      }),
    ).toBe('ok')
    expect(
      dryRunState({
        status: status({ ok: false, time: '2026-08-18T09:00:00Z' }),
        artifactUpdatedAt: '2026-08-18T09:00:02Z',
      }),
    ).toBe('stale')
    expect(
      dryRunState({
        status: status({ ok: false, time: '2026-08-18T09:00:00Z', stage: 'run' }),
        artifactUpdatedAt: '2026-08-18T09:00:00Z',
      }),
    ).toBe('error')
  })

  it('treats a later save of the same failed code as stale', () => {
    expect(
      dryRunState({
        status: status({ ok: false, time: '2026-08-18T09:00:00Z' }),
        artifactUpdatedAt: '2026-08-18T09:00:05Z',
      }),
    ).toBe('stale')
  })
})

describe('labels', () => {
  it('returns badge text and classes', () => {
    expect(dryRunLabel('none')).toBe('Не прогонялся')
    expect(dryRunLabel('ok')).toBe('Прогон ok')
    expect(dryRunLabel('error')).toBe('Ошибка')
    expect(dryRunLabel('stale')).toBe('Устарел')
    expect(dryRunSummaryLabel('none')).toBe('Нужен прогон')
    expect(dryRunSummaryLabel('error')).toBe('Ошибка прогона')
    expect(dryRunSummaryLabel('stale')).toBe('Прогон устарел')
    expect(dryRunBadgeClass('none')).toBe('badge-neutral')
    expect(dryRunBadgeClass('ok')).toBe('badge-success')
    expect(dryRunBadgeClass('error')).toBe('badge-danger')
    expect(dryRunBadgeClass('stale')).toBe('badge-warning')
    expect(stageLabel('validate')).toBe('проверка кода')
    expect(stageLabel('run')).toBe('запуск')
    expect(stageLabel('verify')).toBe('проверки результата')
  })
})

describe('errorLineNo', () => {
  it('prefers lastRun.line_no and falls back to the backend error pattern', () => {
    expect(
      errorLineNo(status({ error: '(line 9: x)' }), { line_no: 3, error: 'other' }),
    ).toBe(3)
    expect(
      errorLineNo(
        status({ error: 'script raised: boom (line 4: return items[0])' }),
        null,
      ),
    ).toBe(4)
    expect(errorLineNo(status({ error: 'no line here' }), null)).toBeNull()
    expect(
      errorSourceLine(
        status({ error: 'script raised: boom (line 4: return items[0])' }),
        null,
      ),
    ).toBe('return items[0]')
  })
})

describe('scriptDryRun', () => {
  it('reads the script slot object and ignores steps arrays', () => {
    const dry = status({ ok: true, time: '2026-08-18T09:00:00Z' })
    expect(scriptDryRun([art('script', 'x', { dry_run: dry })])).toEqual(dry)
    expect(
      scriptDryRun([
        art('script', 'x', { dry_run: [status({ slot: 'steps:0' })] }),
      ]),
    ).toBeNull()
    expect(scriptDryRun([art('meta', '{}')])).toBeNull()
  })
})

describe('buildBlockReason', () => {
  it('hides the hint for agent, missing kind, and a green script run', () => {
    expect(buildBlockReason([art('meta', '{"kind":"agent"}'), art('script', 'x')])).toBeNull()
    expect(buildBlockReason([art('script', 'x')])).toBeNull()
    expect(
      buildBlockReason([
        art('meta', '{"kind":"script"}'),
        art('script', 'x', {
          dry_run: status({ ok: true, time: '2026-08-18T09:00:00Z' }),
        }),
      ]),
    ).toBeNull()
  })

  it('explains a missing, stale, or failed script run', () => {
    expect(
      buildBlockReason([art('meta', '{"kind":"script"}'), art('script', 'x')]),
    ).toBe(
      'Сборка заблокирована: скрипт не прогнан — откройте черновик и нажмите «Прогнать».',
    )
    expect(
      buildBlockReason([
        art('meta', '{"kind":"script"}'),
        art('script', 'x', {
          updated_at: '2026-08-18T10:00:00Z',
          dry_run: status({ ok: false, time: '2026-08-18T09:00:00Z' }),
        }),
      ]),
    ).toBe('Сборка заблокирована: прогон устарел — код менялся после прогона.')
    expect(
      buildBlockReason([
        art('meta', '{"kind":"script"}'),
        art('script', 'x', {
          dry_run: status({
            ok: false,
            time: '2026-08-18T10:00:00Z',
            stage: 'run',
            error: 'boom',
          }),
        }),
      ]),
    ).toBe('Сборка заблокирована: последний прогон упал (запуск).')
  })

  it('lists pipeline script steps that are not green', () => {
    const steps = JSON.stringify({
      steps: [
        { id: 'a', type: 'llm' },
        { id: 'b', type: 'script', code: 'result = 1' },
        { id: 'c', type: 'script', code: 'result = 2' },
      ],
    })
    expect(
      buildBlockReason([
        art('meta', '{"kind":"pipeline"}'),
        art('steps', steps, {
          dry_run: [
            status({ slot: 'steps:1', ok: false, time: null }),
            status({
              slot: 'steps:2',
              ok: true,
              time: '2026-08-18T09:00:00Z',
            }),
          ],
        }),
      ]),
    ).toBe('Сборка заблокирована: script-шаги без зелёного прогона: шаг 2.')
    expect(
      buildBlockReason([
        art('meta', '{"kind":"pipeline"}'),
        art('steps', steps, {
          dry_run: [
            status({ slot: 'steps:1', time: null }),
            status({ slot: 'steps:2', time: null }),
          ],
        }),
      ]),
    ).toBe(
      'Сборка заблокирована: script-шаги без зелёного прогона: шаг 2, шаг 3.',
    )
  })

  it('does not build a pipeline hint from an empty or unparsed dry_run list', () => {
    expect(
      buildBlockReason([
        art('meta', '{"kind":"pipeline"}'),
        art('steps', '{', { is_valid: false, dry_run: [] }),
      ]),
    ).toBeNull()
    expect(
      buildBlockReason([
        art('meta', '{"kind":"pipeline"}'),
        art('steps', JSON.stringify({ steps: [{ id: 'a', type: 'llm' }] }), {
          dry_run: [],
        }),
      ]),
    ).toBeNull()
  })
})
