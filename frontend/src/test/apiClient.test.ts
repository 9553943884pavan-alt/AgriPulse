import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiPostBlob, apiPostForm, apiPost } from '@/api/client'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('API client', () => {
  it('normalizes the backend error envelope', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: {
        code: 'INVALID_PROFILE',
        message: 'Invalid profile',
        user_message: { en: 'Check the farm details.', mr: 'तपशील तपासा.', hi: 'विवरण जांचें।' },
        retryable: false,
        details: { field: 'land_acres' },
      },
    }), { status: 422, headers: { 'Content-Type': 'application/json' } })))

    await expect(apiPost('/api/plan', {})).rejects.toMatchObject({
      apiError: {
        code: 'INVALID_PROFILE',
        user_message: { en: 'Check the farm details.' },
        details: { field: 'land_acres' },
      },
      status: 422,
    })
  })

  it('leaves multipart content type unset so the browser supplies a boundary', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ text: 'transcribed' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)
    const form = new FormData()
    form.append('file', new Blob(['audio']), 'recording.webm')

    await expect(apiPostForm<{ text: string }>('/api/transcribe', form)).resolves.toEqual({ text: 'transcribed' })
    const options = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(new Headers(options.headers).has('Content-Type')).toBe(false)
  })

  it('returns synthesized speech as a binary blob', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Blob(['wav bytes'], { type: 'audio/wav' }), {
      status: 200,
      headers: { 'Content-Type': 'audio/wav' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await apiPostBlob('/api/speak', { text: 'hello', language: 'en' })

    expect(result.type).toBe('audio/wav')
    expect(result).toBeInstanceOf(Blob)
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('Accept')).toBe('audio/wav')
  })
})
