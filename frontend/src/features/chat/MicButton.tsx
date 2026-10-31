/**
 * MicButton — the large microphone button on the Home page.
 * States: idle → recording → transcribing → error.
 *
 * Fix: onAudio is called inside a useEffect, never during render.
 * Fix: startRecording is async — called with void inside handleClick.
 */

import { useEffect } from 'react'
import { Mic, Square, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useRecorder } from './useRecorder'

interface MicButtonProps {
  onAudio: (blob: Blob, mimeType: string) => void
  disabled?: boolean
  size?: 'lg' | 'md'
  hideLabel?: boolean
}

export function MicButton({ onAudio, disabled = false, size = 'lg', hideLabel = false }: MicButtonProps) {
  const { t } = useTranslation()
  const { state, blob, mimeType, elapsed, startRecording, stopRecording, reset } = useRecorder()

  // Fire onAudio when a blob becomes available — NEVER during render
  useEffect(() => {
    if (state === 'transcribing' && blob) {
      onAudio(blob, mimeType)
      reset()
    }
  }, [state, blob, mimeType, onAudio, reset])

  const handleClick = () => {
    if (state === 'recording') {
      stopRecording()
    } else if (state === 'idle') {
      void startRecording()
    }
  }

  const isRecording = state === 'recording'
  const isTranscribing = state === 'transcribing'

  const sizeClasses = size === 'lg' ? 'w-20 h-20' : 'w-12 h-12'
  const iconSize   = size === 'lg' ? 'w-8 h-8'   : 'w-5 h-5'

  return (
    <div className="flex flex-col items-center gap-2">
      <button
        type="button"
        onClick={handleClick}
        disabled={disabled || isTranscribing}
        aria-label={isRecording ? t('home.mic_hold') : t('home.mic_tap')}
        aria-pressed={isRecording}
        className={`
          ${sizeClasses} rounded-full flex items-center justify-center
          transition-all duration-200 focus-visible:outline-none
          focus-visible:ring-4 focus-visible:ring-primary/40
          disabled:opacity-50 disabled:cursor-not-allowed
          ${isRecording
            ? 'bg-primary shadow-[0_0_0_8px_rgba(46,125,50,0.2)] scale-110 animate-pulse'
            : 'bg-primary shadow-card-hover hover:scale-105 active:scale-95'}
        `}
      >
        {isTranscribing ? (
          <Loader2 className={`text-white animate-spin ${iconSize}`} aria-hidden="true" />
        ) : isRecording ? (
          <Square className={`text-white fill-white ${iconSize}`} aria-hidden="true" />
        ) : (
          <Mic className={`text-white ${iconSize}`} aria-hidden="true" />
        )}
      </button>

      <div className="text-center min-h-[1.25rem]" style={{ display: hideLabel ? 'none' : undefined }}>
        {isRecording ? (
          <p className="text-sm font-medium text-primary">
            {elapsed}s — {t('home.mic_hold')}
          </p>
        ) : isTranscribing ? (
          <p className="text-sm text-muted">Transcribing…</p>
        ) : (
          <p className="text-sm text-muted">{t('home.mic_tap')}</p>
        )}
      </div>
    </div>
  )
}
