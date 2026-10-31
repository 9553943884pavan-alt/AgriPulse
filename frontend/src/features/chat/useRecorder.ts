/**
 * useRecorder — MediaRecorder hook with iOS Safari format fallback.
 *
 * iOS Safari records audio/mp4 (not webm). We pick the first supported
 * format in order: webm+opus → mp4 → aac.
 *
 * Max recording: 60 seconds (per frontend spec).
 */

import { useState, useRef, useCallback } from 'react'

export type RecorderState = 'idle' | 'recording' | 'transcribing' | 'error'

const PREFERRED_FORMATS = [
  'audio/webm;codecs=opus',
  'audio/mp4',
  'audio/aac',
  'audio/webm',
]

function getSupportedMimeType(): string {
  for (const fmt of PREFERRED_FORMATS) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(fmt)) {
      return fmt
    }
  }
  return '' // browser default
}

interface UseRecorderReturn {
  state: RecorderState
  blob: Blob | null
  mimeType: string
  elapsed: number       // seconds since recording started
  startRecording: () => void
  stopRecording: () => void
  reset: () => void
}

const MAX_SECONDS = 60

export function useRecorder(): UseRecorderReturn {
  const [state, setState] = useState<RecorderState>('idle')
  const [blob, setBlob] = useState<Blob | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const mediaRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const mimeType = getSupportedMimeType()

  const stopRecording = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    if (mediaRef.current && mediaRef.current.state !== 'inactive') {
      mediaRef.current.stop()
    }
  }, [])

  const startRecording = useCallback(async () => {
    if (state === 'recording') return

    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch {
      setState('error')
      return
    }

    chunksRef.current = []
    const options = mimeType ? { mimeType } : {}
    const recorder = new MediaRecorder(stream, options)
    mediaRef.current = recorder

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data)
    }

    recorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop())
      const recorded = new Blob(chunksRef.current, { type: mimeType || 'audio/webm' })
      setBlob(recorded)
      setState('transcribing')
      setElapsed(0)
    }

    recorder.start(250) // collect in 250 ms chunks
    setState('recording')
    setElapsed(0)

    // Timer — auto-stop at 60 s
    timerRef.current = setInterval(() => {
      setElapsed((prev) => {
        if (prev + 1 >= MAX_SECONDS) {
          stopRecording()
          return MAX_SECONDS
        }
        return prev + 1
      })
    }, 1000)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, mimeType])

  const reset = useCallback(() => {
    setBlob(null)
    setState('idle')
    setElapsed(0)
  }, [])

  return { state, blob, mimeType, elapsed, startRecording, stopRecording, reset }
}
