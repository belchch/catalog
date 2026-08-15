import { describe, expect, it } from 'vitest'
import { parseStepsArtifact } from './api.ts'

describe('parseStepsArtifact', () => {
  it('parses wrapped steps and fills defaults', () => {
    const { steps, parseError } = parseStepsArtifact(
      JSON.stringify({
        steps: [
          { id: 'extract', type: 'script', extra: true },
          {
            id: 'note',
            type: 'llm',
            input: 'previous',
            system_prompt: 'hi',
            allowed_tools: ['read_document'],
            model: 'm',
            provider: 'p',
            reasoning: 'low',
          },
        ],
      }),
    )
    expect(parseError).toBeNull()
    expect(steps).toHaveLength(2)
    expect(steps[0]).toMatchObject({
      id: 'extract',
      type: 'script',
      input: 'documents',
      code: '',
    })
    expect(steps[1]).toMatchObject({
      id: 'note',
      type: 'llm',
      input: 'previous',
      system_prompt: 'hi',
      allowed_tools: ['read_document'],
      model: 'm',
      provider: 'p',
      reasoning: 'low',
    })
  })

  it('accepts a raw array and prompt alias', () => {
    const { steps, parseError } = parseStepsArtifact(
      JSON.stringify([{ type: 'llm', prompt: 'from alias' }]),
    )
    expect(parseError).toBeNull()
    expect(steps[0].system_prompt).toBe('from alias')
    expect(steps[0].input).toBe('documents')
  })

  it('returns parseError on broken JSON without throwing', () => {
    const { steps, parseError } = parseStepsArtifact('{not json')
    expect(steps).toEqual([])
    expect(parseError).toBe('steps must be JSON')
  })

  it('returns parseError when steps is not a list', () => {
    expect(parseStepsArtifact('{"steps":{}}').parseError).toBe('steps must be a list')
    expect(parseStepsArtifact('{"name":"x"}').parseError).toBe('steps must be a list')
    expect(parseStepsArtifact('null').parseError).toBe('steps must be a list')
  })

  it('treats empty content as an empty list', () => {
    expect(parseStepsArtifact('')).toEqual({ steps: [], parseError: null })
    expect(parseStepsArtifact('{"steps":[]}')).toEqual({ steps: [], parseError: null })
  })

  it('skips non-object items', () => {
    const { steps, parseError } = parseStepsArtifact(
      JSON.stringify({ steps: [null, 'x', { id: 'ok', type: 'script' }] }),
    )
    expect(parseError).toBeNull()
    expect(steps.map((s) => s.id)).toEqual(['ok'])
  })
})
