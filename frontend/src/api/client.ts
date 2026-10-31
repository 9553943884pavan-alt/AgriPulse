/**
 * Fetch client for AgriPulse API.
 * Base URL comes from VITE_API_URL environment variable.
 * All JSON responses ≤ 64 KB (mirrors backend rule).
 */

import type { ApiError } from './types'

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

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

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${BASE_URL}${path}`

  let response: Response
  try {
    response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        ...options.headers,
      },
    })
  } catch {
    throw new NetworkError()
  }

  if (!response.ok) {
    let errorBody: ApiError
    try {
      const json = (await response.json()) as { error: ApiError }
      errorBody = json.error
    } catch {
      errorBody = {
        code: 'INTERNAL',
        message: `HTTP ${response.status}`,
        user_message: { en: 'Something went wrong.', mr: 'काहीतरी चुकले.', hi: 'कुछ गलत हो गया.' },
        retryable: response.status >= 500,
        details: {},
      }
    }
    throw new ApiClientError(errorBody, response.status)
  }

  return response.json() as Promise<T>
}

/** POST with a JSON body */
export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** POST multipart/form-data (for audio upload) */
export async function apiPostForm<T>(path: string, form: FormData): Promise<T> {
  return apiFetch<T>(path, {
    method: 'POST',
    headers: {}, // let the browser set Content-Type with boundary
    body: form,
  })
}
