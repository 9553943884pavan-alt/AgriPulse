/**
 * Fetch client for AgriPulse API.
 * Base URL comes from VITE_API_URL environment variable.
 * All JSON responses ≤ 64 KB (mirrors backend rule).
 */

import type { ApiError, FarmProfile, SaveProfileRequest, SaveProfileResponse } from './types'

export const API_BASE_URL = (
  (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'
).replace(/\/+$/, '')

export class ApiClientError extends Error {
  constructor(
    public readonly apiError: ApiError,
    public readonly status: number,
  ) {
    super(apiError.message)
    this.name = 'ApiClientError'
  }
}

export class NetworkError extends Error {
  constructor(message = 'Network request failed') {
    super(message)
    this.name = 'NetworkError'
  }
}

export function normalizeApiError(value: unknown, status: number): ApiError {
  const envelope = isRecord(value) && isRecord(value.error) ? value.error : value
  if (
    isRecord(envelope)
    && typeof envelope.code === 'string'
    && isRecord(envelope.user_message)
  ) {
    const messages = envelope.user_message
    return {
      code: envelope.code,
      message: typeof envelope.message === 'string' ? envelope.message : envelope.code,
      user_message: {
        en: typeof messages.en === 'string' ? messages.en : 'Something went wrong.',
        mr: typeof messages.mr === 'string' ? messages.mr : 'काहीतरी चुकले.',
        hi: typeof messages.hi === 'string' ? messages.hi : 'कुछ गलत हो गया.',
      },
      retryable: typeof envelope.retryable === 'boolean' ? envelope.retryable : status >= 500,
      details: isRecord(envelope.details) ? envelope.details : {},
    }
  }
  return {
    code: 'INTERNAL',
    message: `HTTP ${status}`,
    user_message: {
      en: 'Something went wrong.',
      mr: 'काहीतरी चुकले.',
      hi: 'कुछ गलत हो गया.',
    },
    retryable: status >= 500,
    details: {},
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

async function request(path: string, options: RequestInit): Promise<Response> {
  const headers = new Headers(options.headers)
  if (!headers.has('Accept')) headers.set('Accept', 'application/json')
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData
  if (options.body && !isFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new NetworkError()
  }
  if (!response.ok) {
    let body: unknown
    try {
      body = await response.json()
    } catch {
      body = null
    }
    throw new ApiClientError(normalizeApiError(body, response.status), response.status)
  }
  return response
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await request(path, options)
  return response.json() as Promise<T>
}

/** POST with a JSON body */
export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** PUT with a JSON body */
export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

/**
 * PUT /api/profile: validates and persists the farm profile. It never plans.
 * 422 errors carry per-field messages in apiError.details.fields.
 */
export async function saveProfile(threadId: string | null, profile: FarmProfile): Promise<SaveProfileResponse> {
  const body: SaveProfileRequest = { thread_id: threadId, profile }
  return apiPut<SaveProfileResponse>('/api/profile', body)
}

/** POST multipart/form-data (for audio upload) */
export async function apiPostForm<T>(path: string, form: FormData): Promise<T> {
  return apiFetch<T>(path, {
    method: 'POST',
    headers: {}, // let the browser set Content-Type with boundary
    body: form,
  })
}

/** POST JSON and return a binary response such as synthesized audio. */
export async function apiPostBlob(path: string, body: unknown): Promise<Blob> {
  const response = await request(path, {
    method: 'POST',
    headers: { Accept: 'audio/wav' },
    body: JSON.stringify(body),
  })
  return response.blob()
}
