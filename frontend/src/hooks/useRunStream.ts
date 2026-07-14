import { useCallback, useEffect, useRef, useState } from 'react'
import { connectRun, formatToolArgs, type ServerEvent } from '../ws.ts'

export interface RunStep {
  id: string
  kind: 'step' | 'tool_call' | 'tool_result' | 'verify'
  text: string
  ok?: boolean
  passed?: boolean
  failures?: string[]
  iteration?: number
}

export interface UseRunStreamResult {
  steps: RunStep[]
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
  const [resultText, setResultText] = useState('')
  const [status, setStatus] = useState<string | null>(null)
  const [finished, setFinished] = useState(false)
  const [closed, setClosed] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bufferRef = useRef<string>('')

  const handleEvent = useCallback((e: ServerEvent) => {
    switch (e.type) {
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
        setSteps((prev) => [
          ...prev,
          { id: uniqueId('res'), kind: 'tool_result', text: `← ${e.name}`, ok: e.ok },
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

  return { steps, resultText, status, finished, closed, error }
}
