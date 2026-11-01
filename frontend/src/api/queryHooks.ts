/**
 * TanStack Query hooks — one per backend endpoint that returns cached data.
 * Imperative calls (E1 chat, E3 reoptimize, E5 transcribe, E6 speak) are
 * handled in feature hooks, not here.
 */

import { useMutation, useQuery } from '@tanstack/react-query'
import { apiFetch, apiPost } from './client'
import type {
  ThreadResponse,
  PlanResult,
  District,
  DistrictContext,
  DataSource,
  SourceHealth,
  FarmProfile,
  HealthResponse,
  LocationSearchResult,
  PrefetchResponse,
  SseSchemasResponse,
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
    queryFn: () => apiFetch<ThreadResponse>(`/api/threads/${encodeURIComponent(threadId!)}`),
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
    queryFn: () => apiFetch<DistrictContext>(`/api/districts/${encodeURIComponent(district!)}/context`),
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
    queryFn: () => apiFetch<HealthResponse>('/api/health'),
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

// ---------------------------------------------------------------------------
// E7 POST /api/prefetch — warm location-dependent caches after selection
// ---------------------------------------------------------------------------
export function usePrefetchLocation() {
  return useMutation({
    mutationFn: (location_text: string) =>
      apiPost<PrefetchResponse>('/api/prefetch', { location_text }),
  })
}

// ---------------------------------------------------------------------------
// E8 GET /api/locations/search — Maharashtra location autocomplete
// ---------------------------------------------------------------------------
export function useLocationSearch(query: string) {
  const normalized = query.trim()
  return useQuery({
    queryKey: ['location-search', normalized],
    queryFn: () =>
      apiFetch<LocationSearchResult>(`/api/locations/search?q=${encodeURIComponent(normalized)}&limit=5`),
    enabled: normalized.length >= 2,
    staleTime: 60 * 1000,
    retry: 0,
  })
}

// ---------------------------------------------------------------------------
// C.4 GET /api/schemas/sse-events — schema discovery for contract tooling
// ---------------------------------------------------------------------------
export function useSseSchemas(enabled = false) {
  return useQuery({
    queryKey: ['sse-event-schemas'],
    queryFn: () => apiFetch<SseSchemasResponse>('/api/schemas/sse-events'),
    enabled,
    staleTime: 24 * 60 * 60 * 1000,
    retry: 0,
  })
}
