import { afterEach, describe, expect, it, vi } from 'vitest'
import { streamChat, type SSEHandlers } from '@/api/sseClient'

afterEach(() => {
  vi.unstubAllGlobals()
})

function makeHandlers(): SSEHandlers {
  return {
    onThread: vi.fn(),
    onProfile: vi.fn(),
    onQuestion: vi.fn(),
    onTrace: vi.fn(),
    onPlan: vi.fn(),
    onMessage: vi.fn(),
    onError: vi.fn(),
    onDone: vi.fn(),
    onClose: vi.fn(),
  }
}

function streamResponse(chunks: string[]): Response {
  const encoder = new TextEncoder()
  return new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

describe('SSE client', () => {
  it('parses chunked frames and dispatches the message and done events', async () => {
    const handlers = makeHandlers()
    const frame = [
      ': ping\r\n',
      'event: thread\r\n',
      'data: {"thread_id":"th_123"}\r\n\r\n',
      'event: message\n',
      'data: {"text":"Plan ready","language":"en","provider":"template"}\n\n',
      'event: done\n',
      'data: {"ms":12}\n\n',
    ].join('')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      frame.slice(0, 27),
      frame.slice(27, 74),
      frame.slice(74),
    ])))

    streamChat({ message: 'hello', language: 'en' }, handlers)
    await vi.waitFor(() => expect(handlers.onClose).toHaveBeenCalledOnce())

    expect(handlers.onThread).toHaveBeenCalledWith({ thread_id: 'th_123' })
    expect(handlers.onMessage).toHaveBeenCalledWith({ text: 'Plan ready', language: 'en', provider: 'template' })
    expect(handlers.onDone).toHaveBeenCalledWith({ ms: 12 })
    expect(handlers.onError).not.toHaveBeenCalled()
  })

  it('unwraps the backend error envelope in an error event', async () => {
    const handlers = makeHandlers()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      'event: error\n',
      'data: {"error":{"code":"UPSTREAM_UNAVAILABLE","message":"Unavailable","user_message":{"en":"Try later","mr":"नंतर प्रयत्न करा","hi":"बाद में प्रयास करें"},"retryable":true,"details":{}}}\n\n',
    ])))

    streamChat({ message: 'hello', language: 'en' }, handlers)
    await vi.waitFor(() => expect(handlers.onClose).toHaveBeenCalledOnce())

    expect(handlers.onError).toHaveBeenCalledWith(expect.objectContaining({
      code: 'UPSTREAM_UNAVAILABLE',
      user_message: expect.objectContaining({ en: 'Try later' }),
      retryable: true,
    }))
  })
})
