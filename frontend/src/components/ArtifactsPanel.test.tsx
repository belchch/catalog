import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ScriptDryRunStatus, ScriptTryResult, SessionArtifact } from '../api.ts'
import { ArtifactsPanel } from './ArtifactsPanel.tsx'

afterEach(() => {
  cleanup()
})

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

function dry(extra: Partial<ScriptDryRunStatus> = {}): ScriptDryRunStatus {
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

function tryResult(extra: Partial<ScriptTryResult> = {}): ScriptTryResult {
  return {
    ok: true,
    stage: 'run',
    error: null,
    input_preview: 'in',
    input_len: 2,
    output_preview: 'out',
    output_len: 3,
    output_kind: 'str',
    duration_ms: 128,
    verify: null,
    line_no: null,
    source_line: null,
    ...extra,
  }
}

const CODE = 'result = document\nsecond = 1\nreturn items[0]\n'

function renderPanel(
  artifacts: SessionArtifact[],
  extra: Partial<Parameters<typeof ArtifactsPanel>[0]> = {},
) {
  const onSaveScript =
    extra.onSaveScript ?? vi.fn(async (content: string) => art('script', content))
  const onTryScript = extra.onTryScript ?? vi.fn(async () => tryResult())
  render(
    <ArtifactsPanel
      sessionId="s1"
      artifacts={artifacts}
      loading={false}
      error={null}
      streaming={false}
      highlightType={null}
      onClearHighlight={() => {}}
      onSavePrompt={vi.fn()}
      onSaveMeta={vi.fn()}
      {...extra}
      onSaveScript={onSaveScript}
      onTryScript={onTryScript}
    />,
  )
  return { onSaveScript, onTryScript }
}

describe('ArtifactsPanel script dry-run', () => {
  it('shows «Не прогонялся» when there is no run', () => {
    renderPanel([art('script', CODE), art('meta', '{"kind":"script"}')])
    expect(screen.getByText('Не прогонялся')).toBeTruthy()
    expect(screen.getByText('прогон нужен для сборки')).toBeTruthy()
  })

  it('shows «Прогон ok» for a green payload', () => {
    renderPanel([
      art('meta', '{"kind":"script"}'),
      art('script', CODE, {
        dry_run: dry({ ok: true, time: '2026-08-18T10:00:00Z', stage: 'run' }),
      }),
    ])
    expect(screen.getByText('Прогон ok')).toBeTruthy()
  })

  it('shows an error with a line number from the stored payload', () => {
    renderPanel([
      art('meta', '{"kind":"script"}'),
      art('script', CODE, {
        dry_run: dry({
          ok: false,
          time: '2026-08-18T10:00:00Z',
          stage: 'run',
          error: 'script raised: IndexError (line 3: return items[0])',
        }),
      }),
    ])
    expect(screen.getByText('Ошибка')).toBeTruthy()
    expect(screen.getByText('Ошибка на стадии: запуск')).toBeTruthy()
    expect(screen.getByText('3 │ return items[0]')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Перейти к строке 3' })).toBeTruthy()
  })

  it('marks the status stale after an unsaved edit', () => {
    renderPanel([
      art('meta', '{"kind":"script"}'),
      art('script', CODE, {
        dry_run: dry({ ok: true, time: '2026-08-18T10:00:00Z' }),
      }),
    ])
    fireEvent.change(screen.getByPlaceholderText('Python-скрипт скилла…'), {
      target: { value: `${CODE}\n# edit\n` },
    })
    expect(screen.getByText('Устарел')).toBeTruthy()
    expect(screen.getByText('код сохранится перед прогоном')).toBeTruthy()
    expect(screen.getByText('код менялся после прогона — прогоните снова')).toBeTruthy()
  })

  it('disables Прогнать when the code is empty', () => {
    renderPanel([art('script', ''), art('meta', '{"kind":"script"}')])
    const btn = screen.getByRole('button', { name: 'Прогнать' }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    expect(btn.title).toBe('Добавьте код скрипта')
  })

  it('does not send a second request while a run is in flight', async () => {
    let resolveTry!: (value: ScriptTryResult) => void
    const pending = new Promise<ScriptTryResult>((resolve) => {
      resolveTry = resolve
    })
    const { onTryScript } = renderPanel(
      [art('script', CODE), art('meta', '{"kind":"script"}')],
      { onTryScript: vi.fn(() => pending) },
    )
    const btn = screen.getByRole('button', { name: 'Прогнать' })
    fireEvent.click(btn)
    fireEvent.click(btn)
    expect(onTryScript).toHaveBeenCalledTimes(1)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Прогоняю…' })).toBeTruthy()
    })
    const busy = screen.getByRole('button', { name: 'Прогоняю…' }) as HTMLButtonElement
    expect(busy.disabled).toBe(true)
    expect(busy.getAttribute('aria-busy')).toBe('true')
    fireEvent.click(busy)
    expect(onTryScript).toHaveBeenCalledTimes(1)
    resolveTry(tryResult())
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Прогнать' })).toBeTruthy()
    })
  })

  it('renders collapsed previews and verify after a successful run', async () => {
    const { onTryScript } = renderPanel(
      [art('script', CODE), art('meta', '{"kind":"script"}')],
      {
        onTryScript: vi.fn(async () =>
          tryResult({
            input_preview: `${'x'.repeat(2000)}…[truncated]`,
            input_len: 2500,
            output_preview: 'hello',
            output_len: 5,
            output_kind: 'str',
            duration_ms: 128,
            verify: {
              passed: false,
              failures: ['min_length: короче 200 символов'],
              checks: [
                {
                  check: 'min_length',
                  passed: false,
                  reason: 'короче 200 символов',
                  source: 'builtin',
                  skipped: false,
                },
                {
                  check: 'non_empty',
                  passed: true,
                  reason: null,
                  source: 'builtin',
                  skipped: false,
                },
                {
                  check: 'custom',
                  passed: false,
                  reason: 'нет судьи',
                  source: 'custom',
                  skipped: true,
                },
              ],
            },
          }),
        ),
      },
    )
    fireEvent.click(screen.getByRole('button', { name: 'Прогнать' }))
    await waitFor(() => {
      expect(onTryScript).toHaveBeenCalledTimes(1)
      expect(screen.getByText('Проверки: 1/3')).toBeTruthy()
    })
    expect(screen.getByText('min_length — короче 200 символов')).toBeTruthy()
    expect(screen.getByText('custom — пропущена')).toBeTruthy()
    const input = screen.getByText('Вход (input_preview)').closest('details')
    const output = screen.getByText('Выход (output_preview)').closest('details')
    expect(input?.open).toBe(false)
    expect(output?.open).toBe(false)
    expect(screen.getAllByText('Усечено').length).toBeGreaterThan(0)
    expect(screen.getByText(/показаны первые 2000 симв/)).toBeTruthy()
  })

  it('saves dirty code before the dry-run', async () => {
    const { onSaveScript, onTryScript } = renderPanel([
      art('script', CODE),
      art('meta', '{"kind":"script"}'),
    ])
    fireEvent.change(screen.getByPlaceholderText('Python-скрипт скилла…'), {
      target: { value: `${CODE}\n# edit\n` },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Прогнать' }))
    await waitFor(() => {
      expect(onSaveScript).toHaveBeenCalled()
      expect(onTryScript).toHaveBeenCalledTimes(1)
    })
  })
})
