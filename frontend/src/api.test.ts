import { describe, expect, it } from 'vitest'
import {
  normalizeRunArtifacts,
  parseOutputsArtifact,
  parseStepsArtifact,
  serializeOutputs,
  validateOutputs,
} from './api.ts'

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

  it('keeps type skill and reads snapshot fields from config.kind', () => {
    const { steps, parseError } = parseStepsArtifact(
      JSON.stringify({
        steps: [
          {
            id: 'call_summary',
            type: 'skill',
            input: 'previous',
            skill_id: 'sk_7f3',
            skill_name: 'Сводка',
            config_hash: '1a2b3c4dffff',
            config: { kind: 'agent', system_prompt: 'x' },
          },
        ],
      }),
    )
    expect(parseError).toBeNull()
    expect(steps[0]).toMatchObject({
      id: 'call_summary',
      type: 'skill',
      input: 'previous',
      skill_id: 'sk_7f3',
      skill_name: 'Сводка',
      config_hash: '1a2b3c4dffff',
      skill_kind: 'agent',
    })
  })

  it('tolerates a skill step without snapshot fields', () => {
    const { steps, parseError } = parseStepsArtifact(
      JSON.stringify([{ type: 'skill', skill_id: 'sk_draft' }]),
    )
    expect(parseError).toBeNull()
    expect(steps[0]).toMatchObject({
      type: 'skill',
      skill_id: 'sk_draft',
      skill_name: '',
      config_hash: '',
      skill_kind: '',
    })
  })

  it('still normalizes an unknown type to script', () => {
    const { steps } = parseStepsArtifact(JSON.stringify([{ type: 'other' }]))
    expect(steps[0].type).toBe('script')
  })
})

describe('parseOutputsArtifact', () => {
  it('treats empty content as an empty list', () => {
    expect(parseOutputsArtifact('')).toEqual({ outputs: [], parseError: null, rowErrors: [] })
  })

  it('parses a key/description list', () => {
    const { outputs, parseError } = parseOutputsArtifact(
      JSON.stringify([
        { key: 'brief', description: 'Резюме' },
        { key: 'table', description: 'Таблица' },
      ]),
    )
    expect(parseError).toBeNull()
    expect(outputs).toEqual([
      { key: 'brief', description: 'Резюме' },
      { key: 'table', description: 'Таблица' },
    ])
  })

  it('returns parseError when the payload is not an array', () => {
    expect(parseOutputsArtifact('{not json').parseError).toBe('outputs must be JSON')
    expect(parseOutputsArtifact('{"key":"x"}').parseError).toBe('outputs must be a JSON array')
  })

  it('reads a real boolean multiple flag', () => {
    const { outputs, rowErrors } = parseOutputsArtifact(
      JSON.stringify([{ key: 'chapters', description: 'Главы', multiple: true }]),
    )
    expect(outputs).toEqual([{ key: 'chapters', description: 'Главы', multiple: true }])
    expect(rowErrors).toEqual([null])
  })

  it('does not truthy-coerce a non-boolean multiple and reports a row error', () => {
    const { outputs, parseError, rowErrors } = parseOutputsArtifact(
      JSON.stringify([{ key: 'chapters', description: 'Главы', multiple: 'yes' }]),
    )
    expect(parseError).toBeNull()
    expect(outputs).toEqual([{ key: 'chapters', description: 'Главы' }])
    expect(rowErrors[0]?.multiple).toBe('несколько документов: только true или false')
  })
})

describe('validateOutputs', () => {
  it('accepts an empty list', () => {
    expect(validateOutputs([]).ok).toBe(true)
  })

  it('rejects a bad key, a duplicate, and an empty description', () => {
    const { ok, rowErrors } = validateOutputs([
      { key: 'Brief', description: 'A' },
      { key: 'brief', description: '' },
      { key: 'brief', description: 'B' },
    ])
    expect(ok).toBe(false)
    expect(rowErrors[0]?.key).toBe('ключ: только a-z, цифры и _')
    expect(rowErrors[1]?.description).toBe('описание не может быть пустым')
    expect(rowErrors[2]?.key).toBe('такой ключ уже есть')
  })

  it('accepts a boolean multiple and rejects a non-boolean one', () => {
    const { ok } = validateOutputs([{ key: 'chapters', description: 'Главы', multiple: true }])
    expect(ok).toBe(true)
    const bad = validateOutputs([
      { key: 'chapters', description: 'Главы', multiple: 'yes' as unknown as boolean },
    ])
    expect(bad.ok).toBe(false)
    expect(bad.rowErrors[0]?.multiple).toBe('несколько документов: только true или false')
  })
})

describe('serializeOutputs', () => {
  it('keeps key and description in order', () => {
    expect(
      serializeOutputs([
        { key: 'a', description: 'one' },
        { key: 'b', description: 'two' },
      ]),
    ).toBe(JSON.stringify([
      { key: 'a', description: 'one' },
      { key: 'b', description: 'two' },
    ]))
  })

  it('omits multiple entirely when false or unset, keeping legacy drafts byte-identical', () => {
    expect(
      serializeOutputs([
        { key: 'a', description: 'one', multiple: false },
        { key: 'b', description: 'two' },
      ]),
    ).toBe(
      JSON.stringify([
        { key: 'a', description: 'one' },
        { key: 'b', description: 'two' },
      ]),
    )
  })

  it('writes multiple only when true', () => {
    expect(
      serializeOutputs([{ key: 'chapters', description: 'Главы', multiple: true }]),
    ).toBe(JSON.stringify([{ key: 'chapters', description: 'Главы', multiple: true }]))
  })
})

describe('normalizeRunArtifacts', () => {
  it('reads an array of objects', () => {
    expect(
      normalizeRunArtifacts([
        { key: 'brief', text: 'HELLO', description: 'Резюме' },
        { key: 'table', text: 'A -> a' },
      ]),
    ).toEqual([
      { key: 'brief', text: 'HELLO', description: 'Резюме' },
      { key: 'table', text: 'A -> a' },
    ])
  })

  it('reads a key-to-text dictionary', () => {
    expect(normalizeRunArtifacts({ brief: 'HELLO', table: 'A -> a' })).toEqual([
      { key: 'brief', text: 'HELLO' },
      { key: 'table', text: 'A -> a' },
    ])
  })

  it('returns [] for missing or unknown shapes', () => {
    expect(normalizeRunArtifacts(undefined)).toEqual([])
    expect(normalizeRunArtifacts(null)).toEqual([])
    expect(normalizeRunArtifacts('x')).toEqual([])
  })

  it('reads a collection output as a string array and drops non-string elements', () => {
    expect(
      normalizeRunArtifacts([
        { key: 'chapters', text: ['Ch1', 'Ch2', 1, null], description: 'Главы' },
      ]),
    ).toEqual([{ key: 'chapters', text: ['Ch1', 'Ch2'], description: 'Главы' }])
  })

  it('keeps an empty array as a collection with zero elements', () => {
    expect(normalizeRunArtifacts([{ key: 'chapters', text: [] }])).toEqual([
      { key: 'chapters', text: [] },
    ])
  })

  it('reads a collection output from the key-to-value dictionary shape (the WS finish frame)', () => {
    expect(
      normalizeRunArtifacts({
        index: 'HELLO',
        chapters: ['Ch1', 'Ch2', 'Ch3'],
      }),
    ).toEqual([
      { key: 'index', text: 'HELLO' },
      { key: 'chapters', text: ['Ch1', 'Ch2', 'Ch3'] },
    ])
  })
})
