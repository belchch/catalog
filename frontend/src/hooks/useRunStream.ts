import { useCallback, useEffect, useRef, useState } from 'react'
import {
  connectRun,
  formatToolArgs,
  formatToolResult,
  type ServerEvent,
} from '../ws.ts'

export interface RunMeta {
  model: string
  provider: string
  skillKind: string
  systemPrompt: string
  inputDocs: string[]
}

export interface RunStep {
  id: string
  kind:
    | 'step'
    | 'tool_call'
    | 'tool_result'
    | 'verify'
    | 'script'
    | 'reasoning'
  text: string
  ok?: boolean
  passed?: boolean
  failures?: string[]
  iteration?: number
  // CATALOG-16: tool result payload (previously discarded) + script stage fields.
  result?: string
  stage?: string
  snippet?: string
  returnValue?: string
  duration?: number
  error?: string
}

export interface UseRunStreamResult {
  steps: RunStep[]
  meta: RunMeta | null
  resultText: string
  status: string | null
  finished: boolean
  closed: boolean
  error: string | null
}

let stepCounter = 0
function uniqueId(prefix: string): string {
  stepCounter += 1
  return `${prefix}-${stepCounter}`
}

export function useRunStream(runId: string | null): UseRunStreamResult {
  const [steps, setSteps] = useState<RunStep[]>([])
  const [meta, setMeta] = useState<RunMeta | null>(null)
  const [resultText, setResultText] = useState('')
  const [status, setStatus] = useState<string | null>(null)
  const [finished, setFinished] = useState(false)
  const [closed, setClosed] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bufferRef = useRef<string>('')

  const handleEvent = useCallback((e: ServerEvent) => {
    switch (e.type) {
      case 'meta':
        setMeta({
          model: e.model,
          provider: e.provider,
          skillKind: e.skill_kind,
          systemPrompt: e.system_prompt,
          inputDocs: e.input_docs,
        })
        break
      case 'step':
        setSteps((prev) => [
          ...prev,
          {
            id: uniqueId('step'),
            kind: 'step',
            text: `Итерация ${e.iteration}`,
            iteration: e.iteration,
          },
        ])
        break
      case 'token':
        bufferRef.current += e.delta
        setResultText(bufferRef.current)
        break
      case 'tool_call':
        setSteps((prev) => [
          ...prev,
          {
            id: uniqueId('call'),
            kind: 'tool_call',
            text: `→ ${e.name}(${formatToolArgs(e.arguments)})`,
          },
        ])
        break
      case 'tool_result':
        // CATALOG-16: keep the result payload so the trace can show what the
        // tool returned, not just its name + ok flag.
        setSteps((prev) => [
          ...prev,
          {
            id: uniqueId('res'),
            kind: 'tool_result',
            text: `← ${e.name}`,
            ok: e.ok,
            result: formatToolResult(e.result),
          },
        ])
        break
      case 'verify':
        setSteps((prev) => [
          ...prev,
          {
            id: uniqueId('verify'),
            kind: 'verify',
            text: `Проверка (итерация ${e.iteration})`,
            passed: e.passed,
            failures: e.failures,
            iteration: e.iteration,
          },
        ])
        break
      case 'script':
        setSteps((prev) => [
          ...prev,
          {
            id: uniqueId('script'),
            kind: 'script',
            text:
              e.stage === 'start'
                ? 'Скрипт: запуск'
                : e.stage === 'done'
                  ? 'Скрипт: готово'
                  : 'Скрипт: ошибка',
            stage: e.stage,
            snippet: e.snippet,
            returnValue: e.return_value,
            duration: e.duration,
            error: e.error,
          },
        ])
        break
      case 'reasoning':
        setSteps((prev) => [
          ...prev,
          {
            id: uniqueId('reasoning'),
            kind: 'reasoning',
            text: e.text,
          },
        ])
        break
      case 'finish':
        if (e.status) setStatus(e.status)
        setFinished(true)
        break
      case 'error':
        setError(e.message)
        break
      default:
        break
    }
  }, [])

  useEffect(() => {
    if (!runId) return
    setSteps([])
    setMeta(null)
    setResultText('')
    setStatus(null)
    setFinished(false)
    setClosed(false)
    setError(null)
    bufferRef.current = ''

    const conn = connectRun(runId, handleEvent, {
      onClose: () => setClosed(true),
    })
    return () => conn.close()
  }, [runId, handleEvent])

  return { steps, meta, resultText, status, finished, closed, error }
}
