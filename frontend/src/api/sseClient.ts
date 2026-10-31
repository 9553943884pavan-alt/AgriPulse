/**
 * SSE client for E1 POST /api/agent/chat.
 *
 * Reads a text/event-stream response line-by-line and dispatches each
 * named event to the appropriate handler.  Returns an AbortController so
 * the caller can cancel on unmount or user action.
 */

import type {
  ChatRequest,
  FarmProfile,
  PlanResult,
  TraceEvent,
  ThreadEvent,
  QuestionEvent,
  MessageEvent,
  DoneEvent,
  ApiError,
} from './types'

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

export interface SSEHandlers {
  onThread(e: ThreadEvent): void
  onProfile(e: FarmProfile): void
  onQuestion(e: QuestionEvent): void
  onTrace(e: TraceEvent): void
  onPlan(e: PlanResult): void
  onMessage(e: MessageEvent): void
  onError(e: ApiError): void
  onDone(e: DoneEvent): void
}

/**
 * Open the chat SSE stream.  Returns an AbortController; call .abort() to
 * cancel the stream (e.g. on React component unmount).
 */
export function streamChat(
  body: ChatRequest,
  handlers: SSEHandlers,
): AbortController {
  const controller = new AbortController()

  void (async () => {
    let response: Response
    try {
      response = await fetch(`${BASE_URL}/api/agent/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        handlers.onError({
          code: 'UPSTREAM_UNAVAILABLE',
          message: 'Network error',
          user_message: {
            en: 'Connection failed. Please try again.',
            mr: 'कनेक्शन अयशस्वी. कृपया पुन्हा प्रयत्न करा.',
            hi: 'कनेक्शन विफल। कृपया पुनः प्रयास करें।',
          },
          retryable: true,
          details: {},
        })
      }
      return
    }

    if (!response.ok || !response.body) {
      handlers.onError({
        code: 'INTERNAL',
        message: `HTTP ${response.status}`,
        user_message: {
          en: 'Server error. Please try again.',
          mr: 'सर्व्हर त्रुटी. कृपया पुन्हा प्रयत्न करा.',
          hi: 'सर्वर त्रुटि। कृपया पुनः प्रयास करें।',
        },
        retryable: true,
        details: {},
      })
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let currentEvent = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      // Keep the last (potentially incomplete) line in the buffer
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          const dataStr = line.slice(6).trim()
          if (!dataStr || dataStr === '[DONE]') continue

          try {
            // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
            const payload = JSON.parse(dataStr)
            dispatchEvent(currentEvent, payload, handlers)
          } catch {
            // Ignore malformed JSON lines
          }
          currentEvent = ''
        }
        // Ignore comment lines (heartbeat) — they start with ':'
      }
    }
  })()

  return controller
}

function dispatchEvent(
  event: string,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  payload: any,
  handlers: SSEHandlers,
): void {
  switch (event) {
    case 'thread':
      handlers.onThread(payload as ThreadEvent)
      break
    case 'profile':
      handlers.onProfile(payload as FarmProfile)
      break
    case 'question':
      handlers.onQuestion(payload as QuestionEvent)
      break
    case 'trace':
      handlers.onTrace(payload as TraceEvent)
      break
    case 'plan':
      handlers.onPlan(payload as PlanResult)
      break
    case 'message':
      handlers.onMessage(payload as MessageEvent)
      break
    case 'error':
      handlers.onError(payload as ApiError)
      break
    case 'done':
      handlers.onDone(payload as DoneEvent)
      break
    default:
      break
  }
}
