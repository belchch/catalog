import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { SessionArtifact } from '../api.ts'
import { ArtifactSummaryCard } from './ArtifactSummaryCard.tsx'

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
    updated_at: '2026-01-01T00:00:00Z',
    ...extra,
  }
}

afterEach(cleanup)

describe('ArtifactSummaryCard', () => {
  it('keeps three rows and "из 3" without a steps artifact', () => {
    render(
      <ArtifactSummaryCard
        artifacts={[art('meta', '{"kind":"agent"}'), art('prompt', 'hi')]}
        loading={false}
        error={null}
        streaming={false}
        onOpen={() => {}}
      />,
    )
    expect(screen.getByText('Готово 2 из 3 разделов')).toBeTruthy()
    expect(screen.queryByText('Шаги')).toBeNull()
  })

  it('adds a Шаги row and counts "из 4" when the artifact exists', () => {
    render(
      <ArtifactSummaryCard
        artifacts={[
          art('meta', '{"kind":"pipeline"}'),
          art('steps', JSON.stringify({ steps: [{ id: 'a', type: 'script' }, { id: 'b', type: 'llm' }] })),
          art('prompt', 'hi'),
          art('script', 'result = document'),
        ]}
        loading={false}
        error={null}
        streaming={false}
        onOpen={() => {}}
      />,
    )
    expect(screen.getByText('Готово 4 из 4 разделов')).toBeTruthy()
    expect(screen.getByText('Шаги')).toBeTruthy()
    expect(screen.getByText('2 шага')).toBeTruthy()
  })

  it('counts skill steps and marks prompt/script as not required', () => {
    render(
      <ArtifactSummaryCard
        artifacts={[
          art('meta', '{"kind":"pipeline"}'),
          art(
            'steps',
            JSON.stringify({
              steps: [
                { id: 'a', type: 'skill', skill_id: 'sk_1' },
                { id: 'b', type: 'skill', skill_id: 'sk_2' },
              ],
            }),
          ),
        ]}
        loading={false}
        error={null}
        streaming={false}
        onOpen={() => {}}
      />,
    )
    expect(screen.getByText('Готово 2 из 2 разделов')).toBeTruthy()
    expect(screen.getByText('2 шага')).toBeTruthy()
    expect(screen.getAllByText('не требуется')).toHaveLength(2)
  })

  it('shows a dash when steps are invalid', () => {
    render(
      <ArtifactSummaryCard
        artifacts={[
          art('steps', '{', { is_valid: false, error: 'bad' }),
        ]}
        loading={false}
        error={null}
        streaming={false}
        onOpen={() => {}}
      />,
    )
    expect(screen.getByText('Шаги')).toBeTruthy()
    expect(screen.queryByText('1 шаг')).toBeNull()
    expect(screen.queryByText('2 шага')).toBeNull()
    expect(screen.queryByText(/шагов/)).toBeNull()
  })

  it('shows a dry-run badge on Скрипт without changing the ready count', () => {
    render(
      <ArtifactSummaryCard
        artifacts={[
          art('meta', '{"kind":"script"}'),
          art('prompt', 'hi'),
          art('script', 'result = document'),
        ]}
        loading={false}
        error={null}
        streaming={false}
        onOpen={() => {}}
      />,
    )
    expect(screen.getByText('Готово 3 из 3 разделов')).toBeTruthy()
    expect(screen.getByText('Нужен прогон')).toBeTruthy()
    expect(screen.getAllByText('готово').length).toBeGreaterThan(0)
  })

  it('maps payload states onto the script badge', () => {
    const { rerender } = render(
      <ArtifactSummaryCard
        artifacts={[
          art('script', 'result = document', {
            dry_run: {
              slot: 'script',
              sha256: 'x',
              ok: true,
              stage: 'run',
              error: null,
              time: '2026-08-18T10:00:00Z',
            },
          }),
        ]}
        loading={false}
        error={null}
        streaming={false}
        onOpen={() => {}}
      />,
    )
    expect(screen.getByText('Прогон ok')).toBeTruthy()
    rerender(
      <ArtifactSummaryCard
        artifacts={[
          art('script', 'result = document', {
            dry_run: {
              slot: 'script',
              sha256: 'x',
              ok: false,
              stage: 'run',
              error: 'boom',
              time: '2026-08-18T10:00:00Z',
            },
          }),
        ]}
        loading={false}
        error={null}
        streaming={false}
        onOpen={() => {}}
      />,
    )
    expect(screen.getByText('Ошибка прогона')).toBeTruthy()
    rerender(
      <ArtifactSummaryCard
        artifacts={[
          art('script', 'result = document', {
            updated_at: '2026-08-18T12:00:00Z',
            dry_run: {
              slot: 'script',
              sha256: 'x',
              ok: false,
              stage: 'run',
              error: 'boom',
              time: '2026-08-18T10:00:00Z',
            },
          }),
        ]}
        loading={false}
        error={null}
        streaming={false}
        onOpen={() => {}}
      />,
    )
    expect(screen.getByText('Прогон устарел')).toBeTruthy()
  })
})
