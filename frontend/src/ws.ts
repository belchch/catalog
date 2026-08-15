// WebSocket client for the planner session and run streams (step 06 protocol).
//
// Frames are JSON objects with a discriminating `type`. Reconnect/timeout logic
// is out of scope for this slice: on a close without `finish` the caller shows
// a "connection closed" notice.

import { wsBaseUrl, type DocumentOut, type SessionArtifact } from './api.ts'

export type ServerEvent =
  | { type: 'step'; iteration: number; step_id?: string }
  | { type: 'token'; delta: string; step_id?: string }
  | {
      type: 'tool_call'
      id: string
      name: string
      arguments: Record<string, unknown>
      step_id?: string
    }
  | {
      type: 'tool_result'
      id: string
      name: string
      ok: boolean
      result: unknown
      step_id?: string
    }
  | {
      type: 'verify'
      iteration: number
      passed: boolean
      failures: string[]
      step_id?: string
    }
  | {
      type: 'meta'
      model: string
      provider: string
      skill_kind: string
      system_prompt: string
      input_docs: string[]
    }
  | {
      type: 'script'
      stage: string
      snippet?: string
      return_value?: string
      duration?: number
      error?: string
      step_id?: string
    }
  | { type: 'reasoning'; text: string; step_id?: string }
  | { type: 'suggestions'; items: string[] }
  | { type: 'session_docs'; documents: DocumentOut[] }
  | { type: 'session_artifacts'; artifacts: SessionArtifact[] }
  | {
      type: 'finish'
      capped?: boolean
      status?: string
      output_doc_id?: string | null
      // Raw result text (CATALOG-18) — the apply loop does not stream tokens,
      // so this is the only way the run's text reaches the client.
      result_text?: string | null
    }
  | { type: 'error'; message: string }

export interface PlannerConnection {
  send(text: string, docIds?: string[]): void
  cancel(): void
  close(): void
}

export interface RunConnection {
  cancel(): void
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
    send: (text: string, docIds?: string[]) => {
      if (docIds && docIds.length > 0) {
        ws.send(JSON.stringify({ type: 'user', content: text, doc_ids: docIds }))
      } else {
        ws.send(text)
      }
    },
    cancel: () => ws.send(JSON.stringify({ type: 'cancel' })),
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
  return {
    cancel: () => ws.send(JSON.stringify({ type: 'cancel' })),
    close: () => ws.close(),
  }
}

/** Render tool-call arguments as a compact JSON string (best-effort). */
export function formatToolArgs(args: Record<string, unknown>): string {
  try {
    return JSON.stringify(args)
  } catch {
    return '{...}'
  }
}

/**
 * Render a tool result payload as a compact, human-readable snippet (CATALOG-16).
 * Strings pass through; objects/arrays are JSON-encoded. Bounded by the caller
 * (the backend already truncates the wire frame to ~400 chars).
 */
export function formatToolResult(result: unknown): string {
  if (typeof result === 'string') return result
  try {
    return JSON.stringify(result)
  } catch {
    return String(result)
  }
}
