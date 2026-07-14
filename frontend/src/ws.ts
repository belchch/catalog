// WebSocket client for the planner session and run streams (step 06 protocol).
//
// Frames are JSON objects with a discriminating `type`. Reconnect/timeout logic
// is out of scope for this slice: on a close without `finish` the caller shows
// a "connection closed" notice.

import { wsBaseUrl } from './api.ts'

export type ServerEvent =
  | { type: 'step'; iteration: number }
  | { type: 'token'; delta: string }
  | {
      type: 'tool_call'
      id: string
      name: string
      arguments: Record<string, unknown>
    }
  | { type: 'tool_result'; id: string; name: string; ok: boolean; result: unknown }
  | { type: 'verify'; iteration: number; passed: boolean; failures: string[] }
  | {
      type: 'finish'
      capped?: boolean
      status?: string
      output_doc_id?: string | null
    }
  | { type: 'error'; message: string }

export interface PlannerConnection {
  send(text: string): void
  close(): void
}

export interface RunConnection {
  close(): void
}

interface ConnectOptions {
  onOpen?: () => void
  onClose?: () => void
}

function parseFrame(data: string): ServerEvent | null {
  try {
    return JSON.parse(data) as ServerEvent
  } catch {
    return null
  }
}

export function connectPlanner(
  sessionId: string,
  onEvent: (e: ServerEvent) => void,
  opts?: ConnectOptions,
): PlannerConnection {
  const ws = new WebSocket(`${wsBaseUrl()}/sessions/${sessionId}`)
  ws.onopen = () => opts?.onOpen?.()
  ws.onmessage = (msg: MessageEvent) => {
    const event = parseFrame(msg.data as string)
    if (event) onEvent(event)
  }
  ws.onclose = () => opts?.onClose?.()
  return {
    send: (text: string) => ws.send(text),
    close: () => ws.close(),
  }
}

export function connectRun(
  runId: string,
  onEvent: (e: ServerEvent) => void,
  opts?: ConnectOptions,
): RunConnection {
  const ws = new WebSocket(`${wsBaseUrl()}/runs/${runId}/stream`)
  ws.onopen = () => opts?.onOpen?.()
  ws.onmessage = (msg: MessageEvent) => {
    const event = parseFrame(msg.data as string)
    if (event) onEvent(event)
  }
  ws.onclose = () => opts?.onClose?.()
  return { close: () => ws.close() }
}

/** Render tool-call arguments as a compact JSON string (best-effort). */
export function formatToolArgs(args: Record<string, unknown>): string {
  try {
    return JSON.stringify(args)
  } catch {
    return '{...}'
  }
}
