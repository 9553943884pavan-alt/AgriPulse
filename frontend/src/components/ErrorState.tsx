/**
 * ErrorState — shows an error message from the API.
 *
 * NEVER invents a message. Always uses user_message from the API.
 * The one exception is NetworkError which uses the i18n key errors.network.
 */

import { useTranslation } from 'react-i18next'
import { AlertTriangle } from 'lucide-react'
import type { ApiError, Language } from '@/api/types'
import { useStore } from '@/state/store'

interface ErrorStateProps {
  error: ApiError | null
  /** Network error (no API response) */
  isNetworkError?: boolean
  retryable?: boolean
  onRetry?: () => void
  className?: string
}

export function ErrorState({ error, isNetworkError, retryable, onRetry, className = '' }: ErrorStateProps) {
  const { t } = useTranslation()
  const language = useStore((s) => s.language) as Language

  const message = isNetworkError
    ? t('errors.network')
    : error?.user_message?.[language] ?? error?.message ?? t('errors.network')

  const canRetry = retryable ?? error?.retryable ?? false

  return (
    <div
      role="alert"
      className={`flex flex-col items-center gap-4 rounded-card bg-red-50 border border-danger/20 p-6 text-center ${className}`}
    >
      <AlertTriangle className="w-10 h-10 text-danger" aria-hidden="true" />
      <p className="text-ink font-medium">{message}</p>
      {canRetry && onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="px-4 py-2 rounded-btn bg-primary text-white font-medium text-sm min-h-touch hover:bg-primary-dark transition-colors"
        >
          {t('errors.retry')}
        </button>
      )}
    </div>
  )
}
