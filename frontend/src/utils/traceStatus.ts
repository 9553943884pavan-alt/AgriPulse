/** Header state of the Agent Execution Trace card. */

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
