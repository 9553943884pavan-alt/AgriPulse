/** Header state of the Agent Execution Trace card. */

import type { TraceEvent } from '@/api/types'

export type TraceState = 'live' | 'waiting' | 'failed' | 'done' | 'idle'

export function traceState(opts: {
  isStreaming: boolean
  hasError: boolean
  traceCount: number
  lastTurnWasQuestion: boolean
}): TraceState {
  if (opts.isStreaming) return 'live'
  if (opts.hasError) return 'failed'
  if (opts.traceCount > 0) return 'done'
  if (opts.lastTurnWasQuestion) return 'waiting'
  return 'idle'
}

/* ------------------------------------------------------------------ */
/* Trace display helpers                                               */
/* ------------------------------------------------------------------ */

/** Friendly names for internal step / node / tool identifiers. */
const FRIENDLY_NAMES: Record<string, string> = {
  crop_recommender: 'Crop Recommendation',
  yield_predictor: 'Yield Prediction',
  market_price_service: 'Market Price Analysis',
  water_analyzer: 'Water Availability Analysis',
  cost_calculator: 'Cultivation Cost Estimation',
  optimizer: 'Farm Plan Optimization',
  // Generic orchestration steps that would be meaningless on their own.
  llm: 'AI Reasoning',
  check: 'Input Check',
  complete: 'Completed',
  start: 'Started',
  router: 'Understanding Request',
  route: 'Understanding Request',
}

function humanize(raw: string): string {
  const words = raw
    .replace(/[_\-.]+/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
  return words.map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}

function lookupKey(raw: string | undefined): string | null {
  if (!raw) return null
  const key = raw.trim().toLowerCase().replace(/[\s-]+/g, '_')
  return key in FRIENDLY_NAMES ? FRIENDLY_NAMES[key] : null
}

/** Name to show for a trace row: backend display_name, else a friendly mapping, else a humanized step. */
export function traceDisplayName(event: Pick<TraceEvent, 'step' | 'node'> & Partial<TraceEvent>): string {
  const given = typeof event.display_name === 'string' ? event.display_name.trim() : ''
  if (given) return given
  const mapped = lookupKey(event.step) ?? lookupKey(event.tool_name) ?? lookupKey(event.node)
  if (mapped) return mapped
  const humanized = humanize(event.step || event.tool_name || event.node || '')
  return humanized || 'Working'
}

export const TRACE_SUMMARY_MAX = 200

const UNSAFE_SUMMARY = [
  /Traceback \(most recent call last\)/i,
  /^\s*File ".+", line \d+/m,
  /\b[A-Za-z]+(Error|Exception):\s/,
  /^\s*at\s+\S+\s*\(.+:\d+:\d+\)/m,
  /\bsk-[A-Za-z0-9_-]{8,}/,
  /\bAIza[0-9A-Za-z_-]{10,}/,
  /\bBearer\s+[A-Za-z0-9._-]{8,}/i,
  /\b(api[_-]?key|secret|token|password)\s*[=:]/i,
]

/** Returns a safe, short summary or '' when the text looks like a traceback, JSON or a secret. */
export function sanitizeTraceSummary(summary: unknown): string {
  if (typeof summary !== 'string') return ''
  const text = summary.trim()
  if (!text) return ''
  if (/^[{[]/.test(text)) return ''
  if (UNSAFE_SUMMARY.some((re) => re.test(text))) return ''
  if (text.length > TRACE_SUMMARY_MAX) return `${text.slice(0, TRACE_SUMMARY_MAX - 1).trimEnd()}…`
  return text
}

/**
 * Orders events by backend sequence when every event has one; otherwise keeps
 * arrival order (stable). Does not mutate the input.
 */
export function sortTraceEvents(events: readonly TraceEvent[]): TraceEvent[] {
  const indexed = events.map((event, index) => ({ event, index }))
  const allSequenced = indexed.every(({ event }) => typeof event.sequence === 'number')
  if (allSequenced) {
    indexed.sort((a, b) => (a.event.sequence as number) - (b.event.sequence as number) || a.index - b.index)
  }
  return indexed.map(({ event }) => event)
}
