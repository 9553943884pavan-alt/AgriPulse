/** Pure status logic for the TopBar data/AI badges. */

import type { HealthResponse, SourceHealth } from '@/api/types'

export type BadgeState = 'checking' | 'ok' | 'degraded' | 'down'

interface QueryLike<T> {
  data?: T
  isError: boolean
}

export function dataStatus(q: QueryLike<SourceHealth[]>): BadgeState {
  if (q.isError) return 'down'
  if (!q.data) return 'checking'
  return q.data.every((s) => s.status === 'green') ? 'ok' : 'degraded'
}

/** 'degraded' here means the backend answered but models are still loading. */
export function aiStatus(q: QueryLike<HealthResponse>): BadgeState {
  if (q.isError) return 'down'
  if (!q.data) return 'checking'
  return q.data.status === 'ok' && q.data.models_loaded ? 'ok' : 'degraded'
}

export const BADGE_DOT: Record<BadgeState, string> = {
  checking: 'bg-gray-400',
  ok: 'bg-fresh-leaf animate-pulse',
  degraded: 'bg-amber-500',
  down: 'bg-red-500',
}
