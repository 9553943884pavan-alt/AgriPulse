/**
 * SSE client for E1 POST /api/agent/chat.
 * The returned controller can cancel an active stream.
 */

import { API_BASE_URL, normalizeApiError } from './client'
import type {
  ApiError,
  ChatRequest,
  DoneEvent,
  FarmProfile,
  MessageEvent,
  PlanResult,
  QuestionEvent,
  ThreadEvent,
  TraceEvent,
} from './types'

export interface SSEHandlers {
  onThread(e: ThreadEvent): void
  onProfile(e: FarmProfile): void
  onQuestion(e: QuestionEvent): void
  onTrace(e: TraceEvent): void
  onPlan(e: PlanResult): void
  onMessage(e: MessageEvent): void
  onError(e: ApiError): void
  onDone(e: DoneEvent): void
  onClose?(): void
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function protocolError(message: string): ApiError {
  return {
    code: 'INTERNAL',
    message,
    user_message: {
      en: 'The server returned an invalid response. Please try again.',
      mr: 'सर्व्हरकडून चुकीचा प्रतिसाद मिळाला. कृपया पुन्हा प्रयत्न करा.',
      hi: 'सर्वर से अमान्य उत्तर मिला। कृपया फिर से प्रयास करें।',
    },
    retryable: true,
    details: {},
  }
}

export function streamChat(body: ChatRequest, handlers: SSEHandlers): AbortController {
  const controller = new AbortController()

  void (async () => {
    let response: Response
    try {
      response = await fetch(`${API_BASE_URL}/api/agent/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
    } catch (error) {
      if (!controller.signal.aborted) {
        handlers.onError(
          error instanceof DOMException && error.name === 'AbortError'
            ? protocolError('The chat request was interrupted.')
            : protocolError('Network request failed.'),
        )
      }
      handlers.onClose?.()
      return
    }

    if (!response.ok) {
      let payload: unknown
      try {
        payload = await response.json()
      } catch {
        payload = null
      }
      handlers.onError(normalizeApiError(payload, response.status))
      handlers.onClose?.()
      return
    }

    if (!response.body) {
      handlers.onError(protocolError('The server did not provide an event stream.'))
      handlers.onClose?.()
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let eventName = 'message'
    let dataLines: string[] = []

    const dispatchFrame = () => {
      if (dataLines.length === 0) {
        eventName = 'message'
        return
      }
      const rawData = dataLines.join('\n')
      dataLines = []
      const currentEvent = eventName
      eventName = 'message'
      if (rawData === '[DONE]') return

      let payload: unknown
      try {
        payload = JSON.parse(rawData)
      } catch {
        handlers.onError(protocolError(`Invalid JSON in "${currentEvent}" event.`))
        return
      }
      dispatchEvent(currentEvent, payload, handlers)
    }

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const rawLine of lines) {
          const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine
          if (line === '') {
            dispatchFrame()
          } else if (line.startsWith(':')) {
            continue
          } else if (line.startsWith('event:')) {
            eventName = line.slice(6).trim() || 'message'
          } else if (line.startsWith('data:')) {
            dataLines.push(line.slice(5).replace(/^ /, ''))
          }
        }
      }
      buffer += decoder.decode()
      if (buffer) {
        for (const rawLine of buffer.split('\n')) {
          const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine
          if (line.startsWith('event:')) eventName = line.slice(6).trim() || 'message'
          else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''))
        }
      }
      dispatchFrame()
    } catch (error) {
      if (!controller.signal.aborted) {
        handlers.onError(protocolError(
          error instanceof Error ? `Event stream failed: ${error.message}` : 'Event stream failed.',
        ))
      }
    } finally {
      if (controller.signal.aborted) await reader.cancel().catch(() => undefined)
      handlers.onClose?.()
    }
  })()

  return controller
}

function dispatchEvent(event: string, payload: unknown, handlers: SSEHandlers): void {
  if (!isRecord(payload)) {
    handlers.onError(protocolError(`Invalid payload for "${event}" event.`))
    return
  }

  switch (event) {
    case 'thread':
      if (typeof payload.thread_id === 'string') handlers.onThread({ thread_id: payload.thread_id })
      else handlers.onError(protocolError('Invalid thread event payload.'))
      break
    case 'profile':
      handlers.onProfile(payload as unknown as FarmProfile)
      break
    case 'question':
      if (typeof payload.text === 'string' && typeof payload.field === 'string') {
        handlers.onQuestion(payload as unknown as QuestionEvent)
      } else handlers.onError(protocolError('Invalid question event payload.'))
      break
    case 'trace':
      handlers.onTrace(payload as unknown as TraceEvent)
      break
    case 'plan':
      handlers.onPlan(payload as unknown as PlanResult)
      break
    case 'message':
      if (typeof payload.text === 'string') handlers.onMessage(payload as unknown as MessageEvent)
      else handlers.onError(protocolError('Invalid message event payload.'))
      break
    case 'error':
      handlers.onError(normalizeApiError(payload, 500))
      break
    case 'done':
      if (typeof payload.ms === 'number') {
        handlers.onDone(
          typeof payload.profile_version === 'number'
            ? { ms: payload.ms, profile_version: payload.profile_version }
            : { ms: payload.ms },
        )
      }
      else handlers.onError(protocolError('Invalid done event payload.'))
      break
    default:
      break
  }
}
