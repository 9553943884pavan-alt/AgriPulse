/**
 * TraceTimeline — live-streaming agent trace.
 * Each step shows a colored circle icon matching the reference image.
 */

import { CheckCircle2, AlertCircle, XCircle, MinusCircle, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { TraceEvent } from '@/api/types'
import { SourceBadge } from '@/components/SourceBadge'
import { TraceRowSkeleton } from '@/components/Skeleton'

interface TraceTimelineProps {
  events: TraceEvent[]
  loading?: boolean
  className?: string
}

/** Map step names to emoji/color for the colored circle icon */
function getStepIcon(step: string): { emoji: string; bg: string } {
  const s = step.toLowerCase()
  if (s.includes('farm') || s.includes('understand'))  return { emoji: '🌿', bg: '#dcfce7' }
  if (s.includes('weather'))                           return { emoji: '🌦️', bg: '#dbeafe' }
  if (s.includes('soil'))                              return { emoji: '🪨', bg: '#d6b896' }
  if (s.includes('price'))                             return { emoji: '📊', bg: '#fef9c3' }
  if (s.includes('water'))                             return { emoji: '💧', bg: '#dbeafe' }
  if (s.includes('crop') || s.includes('candidate'))   return { emoji: '🌱', bg: '#dcfce7' }
  if (s.includes('qp') || s.includes('balanced') || s.includes('optim')) return { emoji: '⚙️', bg: '#f0fdf4' }
  if (s.includes('lp') || s.includes('profit'))        return { emoji: '💹', bg: '#fef3c7' }
  return { emoji: '✦', bg: '#f1f5f9' }
}

const STATUS_CHECK: Record<string, React.ReactNode> = {
  running:  <Loader2    className="w-3.5 h-3.5 text-blue-500 animate-spin" aria-hidden="true" />,
  ok:       <CheckCircle2 className="w-3.5 h-3.5 text-green-500" aria-hidden="true" />,
  cached:   <AlertCircle  className="w-3.5 h-3.5 text-amber-500" aria-hidden="true" />,
  failed:   <XCircle      className="w-3.5 h-3.5 text-red-500"   aria-hidden="true" />,
  skipped:  <MinusCircle  className="w-3.5 h-3.5 text-gray-400"  aria-hidden="true" />,
}

export function TraceTimeline({ events, loading, className = '' }: TraceTimelineProps) {
  const { t } = useTranslation()

  if (loading && events.length === 0) {
    return (
      <div className={className}>
        {[1, 2, 3].map((i) => <TraceRowSkeleton key={i} />)}
      </div>
    )
  }

  return (
    <div role="log" aria-live="polite" aria-label="Agent execution trace" className={`space-y-0 ${className}`}>
      {events.map((event) => {
        const { emoji, bg } = getStepIcon(event.step)
        return (
          <div key={event.id} className="flex items-start gap-3 py-2.5 border-b border-gray-50 last:border-0">
            {/* Status check icon */}
            <div className="w-4 flex-shrink-0 mt-1">
              {STATUS_CHECK[event.status] ?? STATUS_CHECK.ok}
            </div>

            {/* Colored circle step icon */}
            <div
              className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 text-sm"
              style={{ background: bg }}
            >
              <span aria-hidden="true">{emoji}</span>
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`text-sm font-semibold ${event.status === 'failed' ? 'text-red-600' : ''}`}
                  style={{ color: event.status === 'failed' ? undefined : '#172B24' }}>
                  {event.step.replace(/_/g, ' ')}
                </span>
                {event.source && (
                  <SourceBadge
                    sourced={{
                      value: 0, unit: '',
                      source: event.source.name,
                      source_url: event.source.url,
                      as_of: '',
                      status: event.source.status,
                    }}
                    compact
                  />
                )}
              </div>
              {event.summary && (
                <p className="text-xs mt-0.5 truncate" style={{ color: '#64748B' }}>{event.summary}</p>
              )}
              {event.fallback_used && (
                <p className="text-xs mt-0.5" style={{ color: '#f59e0b' }}>
                  {t('misc.fallback_used', { fallback: event.fallback_used })}
                </p>
              )}
            </div>

            {/* Duration */}
            {event.duration_ms > 0 && (
              <span className="text-xs flex-shrink-0 tabular-nums" style={{ color: '#94a3b8' }}>
                {(event.duration_ms / 1000).toFixed(1)}s
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}
