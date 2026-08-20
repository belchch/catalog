import { useState } from 'react'
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
      onSaveOutputs={vi.fn(async (content: string) => art('outputs', content))}
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

  it('hides local success previews after a later failed server dry-run', async () => {
    function Harness() {
      const [artifacts, setArtifacts] = useState([
        art('script', CODE),
        art('meta', '{"kind":"script"}'),
      ])
      return (
        <>
          <button
            type="button"
            onClick={() =>
              setArtifacts([
                art('meta', '{"kind":"script"}'),
                art('script', CODE, {
                  dry_run: dry({
                    ok: false,
                    time: '2026-08-18T10:05:00Z',
                    stage: 'run',
                    error: 'script raised: IndexError (line 3: return items[0])',
                  }),
                }),
              ])
            }
          >
            ws-error
          </button>
          <ArtifactsPanel
            sessionId="s1"
            artifacts={artifacts}
            loading={false}
            error={null}
            streaming={false}
            highlightType={null}
            onClearHighlight={() => {}}
            onSavePrompt={vi.fn()}
            onSaveScript={vi.fn(async (content: string) => art('script', content))}
            onSaveMeta={vi.fn()}
            onSaveOutputs={vi.fn(async (content: string) => art('outputs', content))}
            onTryScript={vi.fn(async () => tryResult())}
          />
        </>
      )
    }
    render(<Harness />)
    fireEvent.click(screen.getByRole('button', { name: 'Прогнать' }))
    await waitFor(() => {
      expect(screen.getByText('Выход (output_preview)')).toBeTruthy()
    })
    fireEvent.click(screen.getByRole('button', { name: 'ws-error' }))
    await waitFor(() => {
      expect(screen.getByText('Ошибка')).toBeTruthy()
    })
    expect(screen.queryByText('Выход (output_preview)')).toBeNull()
    expect(screen.queryByText('Вход (input_preview)')).toBeNull()
    expect(screen.getByText('Ошибка на стадии: запуск')).toBeTruthy()
  })

  it('hides local success previews after a save invalidates dry-run', async () => {
    function Harness() {
      const [artifacts, setArtifacts] = useState([
        art('script', CODE),
        art('meta', '{"kind":"script"}'),
      ])
      return (
        <>
          <button
            type="button"
            onClick={() =>
              setArtifacts([
                art('meta', '{"kind":"script"}'),
                art('script', `${CODE}\n# saved\n`, {
                  updated_at: '2026-08-18T10:10:00Z',
                  dry_run: dry({
                    ok: false,
                    time: '2026-08-18T10:00:00Z',
                    stage: 'run',
                  }),
                }),
              ])
            }
          >
            ws-stale
          </button>
          <ArtifactsPanel
            sessionId="s1"
            artifacts={artifacts}
            loading={false}
            error={null}
            streaming={false}
            highlightType={null}
            onClearHighlight={() => {}}
            onSavePrompt={vi.fn()}
            onSaveScript={vi.fn(async (content: string) => art('script', content))}
            onSaveMeta={vi.fn()}
            onSaveOutputs={vi.fn(async (content: string) => art('outputs', content))}
            onTryScript={vi.fn(async () => tryResult())}
          />
        </>
      )
    }
    render(<Harness />)
    fireEvent.click(screen.getByRole('button', { name: 'Прогнать' }))
    await waitFor(() => {
      expect(screen.getByText('Выход (output_preview)')).toBeTruthy()
    })
    fireEvent.click(screen.getByRole('button', { name: 'ws-stale' }))
    await waitFor(() => {
      expect(screen.getByText('Устарел')).toBeTruthy()
    })
    expect(screen.queryByText('Выход (output_preview)')).toBeNull()
  })

  it('keeps local success previews when the code is dirty', async () => {
    renderPanel(
      [art('script', CODE), art('meta', '{"kind":"script"}')],
      { onTryScript: vi.fn(async () => tryResult()) },
    )
    fireEvent.click(screen.getByRole('button', { name: 'Прогнать' }))
    await waitFor(() => {
      expect(screen.getByText('Выход (output_preview)')).toBeTruthy()
    })
    fireEvent.change(screen.getByPlaceholderText('Python-скрипт скилла…'), {
      target: { value: `${CODE}\n# edit\n` },
    })
    expect(screen.getByText('Устарел')).toBeTruthy()
    expect(screen.getByText('Результат относится к предыдущей версии кода')).toBeTruthy()
    expect(screen.getByText('Выход (output_preview)')).toBeTruthy()
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

describe('ArtifactsPanel outputs', () => {
  it('shows the empty outputs card between Meta and Steps', () => {
    renderPanel([art('meta', '{"kind":"agent"}')])
    const headings = screen.getAllByRole('heading')
    const labels = headings.map((el) => el.textContent)
    const metaAt = labels.indexOf('Meta')
    const outputsAt = labels.indexOf('Outputs')
    const stepsAt = labels.indexOf('Steps')
    expect(outputsAt).toBeGreaterThan(metaAt)
    expect(outputsAt).toBeGreaterThan(-1)
    if (stepsAt >= 0) expect(outputsAt).toBeLessThan(stepsAt)
    expect(screen.getByText('Выходов нет — прогон даёт один результат.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Добавить выход' })).toBeTruthy()
  })

  it('renders declared outputs and marks the first as primary', () => {
    renderPanel([
      art(
        'outputs',
        JSON.stringify([
          { key: 'brief', description: 'Резюме' },
          { key: 'table', description: 'Таблица' },
        ]),
      ),
    ])
    expect(screen.getByDisplayValue('brief')).toBeTruthy()
    expect(screen.getByDisplayValue('Резюме')).toBeTruthy()
    expect(screen.getByDisplayValue('table')).toBeTruthy()
    expect(screen.getByText('основной')).toBeTruthy()
  })

  it('moves the primary badge when a row is raised', () => {
    renderPanel([
      art(
        'outputs',
        JSON.stringify([
          { key: 'brief', description: 'Резюме' },
          { key: 'table', description: 'Таблица' },
        ]),
      ),
    ])
    fireEvent.click(screen.getByRole('button', { name: 'Поднять выход table' }))
    const rows = screen.getAllByText('основной')
    expect(rows).toHaveLength(1)
    expect(screen.getByDisplayValue('table')).toBeTruthy()
    const firstKey = document.getElementById('outputs-key-0') as HTMLInputElement
    expect(firstKey.value).toBe('table')
  })

  it('does not PATCH when client validation fails', async () => {
    const onSaveOutputs = vi.fn(async (content: string) => art('outputs', content))
    renderPanel([art('outputs', '[]')], { onSaveOutputs })
    fireEvent.click(screen.getByRole('button', { name: 'Добавить выход' }))
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить outputs' }))
    await waitFor(() => {
      expect(screen.getByText('ключ: только a-z, цифры и _')).toBeTruthy()
    })
    expect(onSaveOutputs).not.toHaveBeenCalled()
  })

  it('shows a server validation error on the card', () => {
    renderPanel([
      art(
        'outputs',
        JSON.stringify([{ key: 'brief', description: 'Резюме' }]),
        { is_valid: false, error: 'duplicate output key' },
      ),
    ])
    expect(screen.getByText('duplicate output key')).toBeTruthy()
    const card = screen.getByText('Outputs').closest('[aria-invalid="true"]')
    expect(card).toBeTruthy()
  })

  it('disables output fields while streaming', () => {
    renderPanel(
      [
        art(
          'outputs',
          JSON.stringify([{ key: 'brief', description: 'Резюме' }]),
        ),
      ],
      { streaming: true },
    )
    expect((screen.getByDisplayValue('brief') as HTMLInputElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: 'Добавить выход' }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: 'Сохранить outputs' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('saves a valid outputs draft', async () => {
    const onSaveOutputs = vi.fn(async (content: string) => art('outputs', content))
    renderPanel([art('outputs', '[]')], { onSaveOutputs })
    fireEvent.click(screen.getByRole('button', { name: 'Добавить выход' }))
    fireEvent.change(screen.getByLabelText('ключ'), { target: { value: 'brief' } })
    fireEvent.change(screen.getByLabelText('описание'), { target: { value: 'Резюме' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить outputs' }))
    await waitFor(() => {
      expect(onSaveOutputs).toHaveBeenCalledWith(
        JSON.stringify([{ key: 'brief', description: 'Резюме' }]),
      )
    })
  })

  it('persists the "несколько документов" toggle through the outputs PATCH', async () => {
    const onSaveOutputs = vi.fn(async (content: string) => art('outputs', content))
    renderPanel(
      [art('outputs', JSON.stringify([{ key: 'chapters', description: 'Главы' }]))],
      { onSaveOutputs },
    )
    const checkbox = screen.getByRole('checkbox', { name: 'несколько документов' })
    expect((checkbox as HTMLInputElement).checked).toBe(false)
    fireEvent.click(checkbox)
    expect((checkbox as HTMLInputElement).checked).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить outputs' }))
    await waitFor(() => {
      expect(onSaveOutputs).toHaveBeenCalledWith(
        JSON.stringify([{ key: 'chapters', description: 'Главы', multiple: true }]),
      )
    })
  })

  it('shows a row error for a non-boolean multiple value from the artifact', () => {
    renderPanel([
      art(
        'outputs',
        JSON.stringify([{ key: 'chapters', description: 'Главы', multiple: 'yes' }]),
      ),
    ])
    expect(screen.getByText('несколько документов: только true или false')).toBeTruthy()
    expect(
      screen.getByRole('checkbox', { name: 'несколько документов' }).getAttribute('aria-invalid'),
    ).toBe('true')
  })
})
