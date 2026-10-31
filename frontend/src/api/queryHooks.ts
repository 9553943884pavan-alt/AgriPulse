/**
 * TanStack Query hooks — one per backend endpoint that returns cached data.
 * Imperative calls (E1 chat, E3 reoptimize, E5 transcribe, E6 speak) are
 * handled in feature hooks, not here.
 */

import { useQuery } from '@tanstack/react-query'
import { apiFetch, apiPost } from './client'
import type {
  ThreadResponse,
  PlanResult,
  District,
  DataSource,
  SourceHealth,
  FarmProfile,
} from './types'

// ---------------------------------------------------------------------------
// E2 POST /api/plan — direct plan from a complete profile (no agent)
// ---------------------------------------------------------------------------
export function usePlan(profile: FarmProfile | null) {
  return useQuery({
    queryKey: ['plan', profile],
    queryFn: () => apiPost<PlanResult>('/api/plan', profile),
    enabled: profile !== null,
    staleTime: 24 * 60 * 60 * 1000, // 24 h — matches backend plan store TTL
    retry: 1,
  })
}

// ---------------------------------------------------------------------------
// E4 GET /api/threads/{thread_id}
// ---------------------------------------------------------------------------
export function useThread(threadId: string | null) {
  return useQuery({
    queryKey: ['thread', threadId],
    queryFn: () => apiFetch<ThreadResponse>(`/api/threads/${threadId}`),
    enabled: threadId !== null,
    staleTime: 24 * 60 * 60 * 1000,
    retry: 1,
  })
}

// ---------------------------------------------------------------------------
// E9 GET /api/districts
// ---------------------------------------------------------------------------
export function useDistricts() {
  return useQuery({
    queryKey: ['districts'],
    queryFn: () => apiFetch<{ districts: District[] }>('/api/districts').then(r => r.districts),
    staleTime: 60 * 60 * 1000, // 1 h
    retry: 2,
  })
}

// ---------------------------------------------------------------------------
// E10 GET /api/districts/{district}/context
// ---------------------------------------------------------------------------
export function useDistrictContext(district: string | null) {
  return useQuery({
    queryKey: ['district-context', district],
    queryFn: () => apiFetch<Record<string, unknown>>(`/api/districts/${district}/context`),
    enabled: district !== null,
    staleTime: 60 * 60 * 1000,
    retry: 1,
  })
}

// ---------------------------------------------------------------------------
// E11 GET /api/sources
// ---------------------------------------------------------------------------
export function useSources() {
  return useQuery({
    queryKey: ['sources'],
    queryFn: () => apiFetch<{ sources: DataSource[] }>('/api/sources').then(r => r.sources),
    staleTime: 10 * 60 * 1000, // 10 min
    retry: 1,
  })
}

// ---------------------------------------------------------------------------
// E12 GET /api/sources/health
// ---------------------------------------------------------------------------
export function useSourcesHealth() {
  return useQuery({
    queryKey: ['sources-health'],
    queryFn: () =>
      apiFetch<{ checked_at: string; sources: SourceHealth[] }>('/api/sources/health').then(
        r => r.sources,
      ),
    staleTime: 60 * 1000, // 1 min — matches backend 60 s cache
    refetchInterval: 60 * 1000,
    retry: 0,
  })
}

// ---------------------------------------------------------------------------
// E13 GET /api/health — used for cold-start polling
// ---------------------------------------------------------------------------
export function useHealth(enabled = true) {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => apiFetch<{ status: string; models_loaded: boolean; data_files: number }>('/api/health'),
    enabled,
    staleTime: 30 * 1000,
    refetchInterval: (query) => {
      // Keep polling until the server is healthy
      const data = query.state.data
      if (data && data.status === 'ok' && data.models_loaded) return false
      return 3000 // poll every 3 s while waking up
    },
    retry: 10,
    retryDelay: 3000,
  })
}
