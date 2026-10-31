/**
 * SourceBadge — appears next to EVERY farmer-visible number.
 *
 * The automated test (FE.T1 "no number without a badge") renders a full
 * PlanResult and fails if any farmer-visible number lacks a SourceBadge.
 *
 * Status → dot color mapping is fixed (backend SPECS.md 5.1):
 *   live            green
 *   cached          amber  (shows "as of <date>")
 *   official_dataset blue  (shows year)
 *   model           purple
 *   computed        grey
 *   farmer_input    grey
 *   assumption      orange (shows disclaimer note)
 */

import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import type { SourcedValue, SourceStatus } from '@/api/types'

const DOT_CLASSES: Record<SourceStatus, string> = {
  live:             'bg-badge-live',
  cached:           'bg-badge-cached',
  official_dataset: 'bg-badge-official',
  model:            'bg-badge-model',
  computed:         'bg-badge-computed',
  farmer_input:     'bg-badge-farmer',
  assumption:       'bg-badge-assumption',
}

interface SourceBadgeProps {
  /** The full SourcedValue object from the API */
  sourced: SourcedValue
  /** If true, renders a smaller inline dot only (no label) */
  compact?: boolean
  className?: string
}

export function SourceBadge({ sourced, compact = false, className = '' }: SourceBadgeProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const dotClass = DOT_CLASSES[sourced.status] ?? 'bg-badge-computed'
  const label = t(`source_status.${sourced.status}`)

  // Close tooltip when clicking outside
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div ref={ref} className={`relative inline-flex items-center gap-1 ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-xs font-medium bg-gray-100 hover:bg-gray-200 transition-colors"
        aria-label={`Data source: ${label}. Tap for details.`}
        aria-expanded={open}
      >
        {/* Status dot */}
        <span className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${dotClass}`} aria-hidden="true" />
        {!compact && (
          <span className="text-muted leading-none">{label}</span>
        )}
      </button>

      {/* Tooltip popover */}
      {open && (
        <div
          role="tooltip"
          className="absolute z-50 bottom-full left-0 mb-2 w-64 rounded-card bg-ink text-surface text-xs p-3 shadow-card-hover"
        >
          <p className="font-semibold mb-1">{label}</p>
          <p className="text-gray-300 mb-1">{sourced.source}</p>
          {sourced.as_of && (
            <p className="text-gray-400">
              {sourced.status === 'cached' ? `As of: ${sourced.as_of}` : `Year: ${sourced.as_of}`}
            </p>
          )}
          {sourced.source_url && (
            <a
              href={sourced.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary-light mt-1 block truncate"
            >
              {sourced.source_url}
            </a>
          )}
          {sourced.status === 'assumption' && (
            <p className="mt-1 text-accent">
              {t('source_status.assumption')}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
