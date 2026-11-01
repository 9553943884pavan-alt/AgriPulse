/**
 * HomePage — 3-column layout:
 *   [Sidebar ~280px via AppShell] | [Chat center ~52%] | [Right panel ~30%]
 *
 * Chat is ChatGPT-style: user msgs right (dark green), agent left (white card).
 * Fixed header + fixed composer. Only message history scrolls.
 * Suggested quick-questions float above composer (always visible).
 * Right panel: Agent Execution Trace + Current Plan Preview.
 */

import { useState, useRef, useCallback, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Send, Volume2, Copy, ThumbsUp, ThumbsDown, Zap,
  Sprout, Cloud, BarChart2, Droplets, IndianRupee,
} from 'lucide-react'
import { MicButton } from '@/features/chat/MicButton'
import { TraceTimeline } from '@/features/trace/TraceTimeline'
import { SummaryTiles } from '@/features/plan/SummaryTiles'
import { ErrorState } from '@/components/ErrorState'
import { useStore } from '@/state/store'
import { streamChat } from '@/api/sseClient'
import { apiPostForm } from '@/api/client'
import { getCropEmoji } from '@/utils/cropEmoji'
import type { FarmProfile, PlanResult, ApiError, Language } from '@/api/types'

/* ─── Suggested quick questions ────────────────────────────────── */
interface SuggestedQuestion {
  icon: React.ReactNode
  text: string
  color: string
}

/* ─── Chat message with timestamp ──────────────────────────────── */
interface DisplayMessage {
  role: 'farmer' | 'agent'
  text: string
  ts: string   // e.g. "10:28 PM"
}

function formatTime(iso?: string): string {
  const d = iso ? new Date(iso) : new Date()
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/* ─── Agent avatar ─────────────────────────────────────────────── */
function AgentAvatar() {
  return (
    <div
      className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm overflow-hidden flex-shrink-0"
      style={{ background: '#e8f8f0', border: '2px solid #86efac' }}
    >
      <span className="text-[18px] leading-none" aria-hidden="true">🤖</span>
    </div>
  )
}

/* ─── User avatar ──────────────────────────────────────────────── */
function UserAvatar() {
  return (
    <div
      className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm"
      style={{ background: '#94a3b8' }}
    >
      <span className="text-[15px] leading-none" aria-hidden="true">👤</span>
    </div>
  )
}

/* ─── Botanical leaf decorations ───────────────────────────────── */
function BotanicalLeaf({ className }: { className: string }) {
  return (
    <div className={`absolute pointer-events-none select-none ${className}`} aria-hidden="true">
      <svg viewBox="0 0 60 80" className="w-full h-full" xmlns="http://www.w3.org/2000/svg">
        <path
          d="M30,75 Q5,50 15,20 Q25,0 30,5 Q35,0 45,20 Q55,50 30,75Z"
          fill="#22C55E" opacity="0.12"
        />
        <path
          d="M30,70 Q30,40 20,18"
          stroke="#22C55E" strokeWidth="1" fill="none" opacity="0.2"
        />
      </svg>
    </div>
  )
}

export function HomePage() {
  const { t } = useTranslation()
  const {
    threadId, language, plan, selectedScenario,
    setThreadId, setProfile, setPlan, addMessage, addTraceEvent,
    messages: storedMessages, traceEvents,
  } = useStore()

  const SUGGESTED: SuggestedQuestion[] = [
    { icon: <Sprout className="w-3.5 h-3.5" />,      text: t('home.q1'),  color: '#22C55E' },
    { icon: <Cloud className="w-3.5 h-3.5" />,       text: t('home.q2'),  color: '#0ea5e9' },
    { icon: <Sprout className="w-3.5 h-3.5" />,      text: t('home.q3'),  color: '#f59e0b' },
    { icon: <BarChart2 className="w-3.5 h-3.5" />,   text: t('home.q4'),  color: '#8b5cf6' },
    { icon: <Droplets className="w-3.5 h-3.5" />,    text: 'Estimate my water requirement', color: '#0ea5e9' },
    { icon: <IndianRupee className="w-3.5 h-3.5" />, text: 'Get latest market prices',      color: '#f59e0b' },
  ]

  const [inputText, setInputText] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  const [chatMessages, setChatMessages] = useState<DisplayMessage[]>(() => {
    if (storedMessages.length > 0) {
      return storedMessages.map((m) => ({
        role: m.role,
        text: m.text,
        ts: formatTime(m.at),
      }))
    }
    return [{ role: 'agent', text: t('home.greeting'), ts: formatTime() }]
  })

  const abortRef = useRef<AbortController | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => { scrollToBottom() }, [chatMessages, isStreaming, scrollToBottom])

  const sendMessage = useCallback((text: string) => {
    if (!text.trim() || isStreaming) return
    setError(null)
    setIsStreaming(true)
    setInputText('')

    const now = formatTime()
    const farmerMsg: DisplayMessage = { role: 'farmer', text, ts: now }
    setChatMessages((prev) => [...prev, farmerMsg])
    addMessage({ role: 'farmer', text, language: language as Language, at: new Date().toISOString() })

    const controller = streamChat(
      { thread_id: threadId ?? undefined, message: text, language: language as Language },
      {
        onThread: (e) => setThreadId(e.thread_id),
        onProfile: (e: FarmProfile) => setProfile(e),
        onQuestion: (e) => {
          setChatMessages((prev) => [...prev, { role: 'agent', text: e.text, ts: formatTime() }])
          addMessage({ role: 'agent', text: e.text, language: language as Language, at: new Date().toISOString() })
          setIsStreaming(false)
        },
        onTrace: (e) => addTraceEvent(e),
        onPlan: (e: PlanResult) => setPlan(e),
        onMessage: (e) => {
          setChatMessages((prev) => [...prev, { role: 'agent', text: e.text, ts: formatTime() }])
          addMessage({ role: 'agent', text: e.text, language: language as Language, at: new Date().toISOString() })
        },
        onError: (e: ApiError) => { setError(e); setIsStreaming(false) },
        onDone: () => setIsStreaming(false),
      },
    )
    abortRef.current = controller
    setTimeout(() => inputRef.current?.focus(), 50)
  }, [isStreaming, threadId, language, addMessage, addTraceEvent, setThreadId, setProfile, setPlan])

  const handleAudio = useCallback(async (blob: Blob, mimeType: string) => {
    const form = new FormData()
    form.append('audio', blob, `recording.${mimeType.includes('mp4') ? 'mp4' : 'webm'}`)
    form.append('language_hint', language)
    try {
      const result = await apiPostForm<{ text: string; language: string }>('/api/transcribe', form)
      sendMessage(result.text)
    } catch {
      setError({
        code: 'STT_FAILED',
        message: 'Speech recognition failed',
        user_message: { en: t('errors.speech_failed'), mr: t('errors.speech_failed'), hi: t('errors.speech_failed') },
        retryable: true,
        details: {},
      })
    }
  }, [language, sendMessage, t])

  useEffect(() => { return () => { abortRef.current?.abort() } }, [])

  const lang = language as Language

  return (
    <div className="flex h-full overflow-hidden">

      {/* ═══════════════════════════════════════════════════════════
          CENTER — Chat panel (~50%)
      ════════════════════════════════════════════════════════════ */}
      <div
        className="flex flex-col min-h-0 overflow-hidden relative flex-shrink-0"
        style={{
          width: '50%',
          maxWidth: '720px',
          minWidth: '420px',
          background: '#F7F8EE',
          borderRight: '1px solid #D9EBCB',
        }}
      >
        {/* Botanical leaf decorations */}
        <BotanicalLeaf className="top-16 right-2 w-12 h-16 rotate-12 opacity-70" />
        <BotanicalLeaf className="top-40 right-0 w-10 h-14 rotate-45 opacity-50" />
        <BotanicalLeaf className="bottom-32 left-1 w-10 h-14 -rotate-12 opacity-60" />
        <BotanicalLeaf className="bottom-60 right-2 w-8 h-12 rotate-30 opacity-40" />

        {/* ── Chat header (fixed) ──────────────────────────────── */}
        <div
          className="flex items-center justify-between px-6 py-4 flex-shrink-0 z-10"
          style={{
            background: 'rgba(247,248,238,0.95)',
            backdropFilter: 'blur(8px)',
            borderBottom: '1px solid #D9EBCB',
          }}
        >
          <div className="flex items-center gap-3">
            {/* Large leaf SVG icon — matches theme */}
            <div
              className="w-12 h-12 rounded-2xl flex items-center justify-center flex-shrink-0 shadow-md"
              style={{ background: 'linear-gradient(135deg, #073B2B, #16834A)' }}
            >
              <svg viewBox="0 0 24 24" className="w-7 h-7" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                <path d="M12 22C12 22 4 16 4 9C4 5.134 7.582 2 12 2C16.418 2 20 5.134 20 9C20 16 12 22 12 22Z" fill="#16834A" />
                <path d="M12 22V9" stroke="#073B2B" strokeWidth="1.5" strokeLinecap="round" />
                <path d="M12 14C14 12 17 11 19 12" stroke="#073B2B" strokeWidth="1.2" strokeLinecap="round" />
                <path d="M12 10C10 8 7 7 5 8" stroke="#073B2B" strokeWidth="1.2" strokeLinecap="round" />
              </svg>
            </div>
            <div>
              <h1 className="text-[18px] font-bold leading-tight" style={{ color: '#09231A' }}>
                Talk to <span style={{ color: '#16834A' }}>AgriPulse</span>
              </h1>
              <p className="text-xs mt-0.5 leading-tight" style={{ color: '#52685E' }}>
                {t('home.subtitle')}
              </p>
            </div>
          </div>
          <button
            type="button"
            aria-label="Toggle audio output"
            className="w-9 h-9 rounded-full flex items-center justify-center transition-colors hover:opacity-80"
            style={{ background: '#D9EBCB', border: '1px solid #bcd8a6' }}
          >
            <Volume2 className="w-4 h-4" style={{ color: '#073B2B' }} aria-hidden="true" />
          </button>
        </div>

        {/* ── Suggested chips ──────────────────────────────────── */}
        <div
          className="flex-shrink-0 px-5 pt-3 pb-2"
          style={{ borderBottom: chatMessages.length <= 1 ? '1px solid #D9EBCB' : 'none' }}
        >
          <div
            className={`gap-2 ${chatMessages.length <= 1 ? 'flex flex-wrap' : 'flex overflow-x-auto pb-1 hide-scrollbar'}`}
            style={{ scrollbarWidth: 'none' }}
          >
            {SUGGESTED.map((q) => (
              <button
                key={q.text}
                type="button"
                onClick={() => sendMessage(q.text)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-150 hover:shadow-md hover:-translate-y-0.5 active:scale-95 flex-shrink-0"
                style={{
                  background: '#fff',
                  border: `1px solid ${q.color}50`,
                  color: '#172B24',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
                }}
              >
                <span style={{ color: q.color }}>{q.icon}</span>
                {q.text}
              </button>
            ))}
          </div>
        </div>

        {/* ── Message history (scrollable) ─────────────────────── */}
        <div
          className="flex-1 overflow-y-auto min-h-0 px-5 py-4 space-y-5 bg-nature-content"
          style={{
            scrollbarWidth: 'thin',
            scrollbarColor: '#16834A transparent',
          }}
        >
          {chatMessages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === 'farmer' ? 'justify-end' : 'justify-start'} items-end gap-2`}
              style={{ animation: 'msgIn 0.25s ease-out' }}
            >
              {/* Agent avatar on left */}
              {msg.role === 'agent' && <AgentAvatar />}

              <div className={`flex flex-col ${msg.role === 'farmer' ? 'items-end' : 'items-start'} max-w-[75%]`}>
                {/* Bubble */}
                <div
                  className="rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm"
                  style={
                    msg.role === 'farmer'
                      ? {
                          background: '#073B2B',
                          color: '#fff',
                          borderBottomRightRadius: 4,
                          maxWidth: '100%',
                        }
                      : {
                          background: '#FFFFFF',
                          color: '#09231A',
                          border: '1px solid #D9EBCB',
                          borderBottomLeftRadius: 4,
                        }
                  }
                >
                  <p className="whitespace-pre-wrap">{msg.text}</p>
                </div>

                {/* Timestamp + actions */}
                <div className="flex items-center gap-2 mt-1 px-1">
                  <span className="text-[10px]" style={{ color: '#52685E' }}>{msg.ts}</span>
                  {msg.role === 'agent' && (
                    <div className="flex items-center gap-1">
                      <button type="button" aria-label="Copy" onClick={() => void navigator.clipboard.writeText(msg.text)} className="p-1 rounded hover:bg-sage-mist/20 transition-colors">
                        <Copy className="w-3 h-3" style={{ color: '#52685E' }} />
                      </button>
                      <button type="button" aria-label="Like" className="p-1 rounded hover:bg-sage-mist/20 transition-colors">
                        <ThumbsUp className="w-3 h-3" style={{ color: '#52685E' }} />
                      </button>
                      <button type="button" aria-label="Dislike" className="p-1 rounded hover:bg-sage-mist/20 transition-colors">
                        <ThumbsDown className="w-3 h-3" style={{ color: '#52685E' }} />
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* User avatar on right */}
              {msg.role === 'farmer' && <UserAvatar />}
            </div>
          ))}

          {/* Streaming indicator */}
          {isStreaming && (
            <div className="flex justify-start items-end gap-2">
              <AgentAvatar />
              <div
                className="rounded-2xl px-4 py-3 shadow-sm"
                style={{ background: '#fff', border: '1px solid #D9EBCB', borderBottomLeftRadius: 4 }}
              >
              <div className="flex gap-1.5 items-center py-1">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="w-2 h-2 rounded-full"
                      style={{
                        background: '#16834A',
                        animation: `typingDot 1.2s ease-in-out ${i * 0.2}s infinite`,
                      }}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}

          {error && (
            <ErrorState error={error} retryable={error.retryable} onRetry={() => setError(null)} />
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* ── Message composer ─────────────────────────────────── */}
        <div
          className="flex items-center gap-3 px-4 py-3 flex-shrink-0"
          style={{
            background: 'rgba(247,248,238,0.97)',
            backdropFilter: 'blur(8px)',
            borderTop: '1px solid #D9EBCB',
          }}
        >
          {/* Mic — large dark-green circle (52px matches reference) */}
          <div className="flex-shrink-0">
            <MicButton onAudio={(blob, mime) => void handleAudio(blob, mime)} disabled={isStreaming} size="md" hideLabel />
          </div>

          {/* Text input — pill shaped */}
          <div
            className="flex-1 flex items-center rounded-full px-4 py-2.5 bg-white border border-sage-mist shadow-xs focus-within:ring-2 focus-within:ring-fresh-leaf transition-all"
          >
            <input
              ref={inputRef}
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) sendMessage(inputText) }}
              placeholder="Ask AgriPulse anything..."
              disabled={isStreaming}
              aria-label="Chat message"
              className="flex-1 bg-transparent text-sm outline-none placeholder-gray-400"
              style={{ color: '#09231A' }}
            />
          </div>

          {/* Send — Forest Green circle (#073B2B) */}
          <button
            type="button"
            onClick={() => sendMessage(inputText)}
            disabled={!inputText.trim() || isStreaming}
            aria-label="Send message"
            className="w-12 h-12 rounded-full flex items-center justify-center flex-shrink-0 shadow-md transition-all hover:scale-105 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed bg-forest hover:bg-fresh-leaf text-white"
          >
            <Send className="w-5 h-5 text-white" aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════
          RIGHT — Trace + Plan (takes all remaining space)
      ════════════════════════════════════════════════════════════ */}
      <div
        className="flex-1 min-w-0 flex flex-col gap-4 p-4 lg:p-5 overflow-y-auto bg-warm-cream w-full"
        style={{
          scrollbarWidth: 'thin',
          scrollbarColor: '#16834A transparent',
        }}
      >

        {/* ── Agent Execution Trace ────────────────────────────── */}
        <div
          className="rounded-2xl p-4 lg:p-5 flex-shrink-0 bg-white border border-sage-mist/80 shadow-card w-full"
        >
          {/* Header */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center bg-sunrise-gold/20"
              >
                <Zap className="w-4 h-4 text-sunrise-gold" aria-hidden="true" />
              </div>
              <span className="text-sm font-bold text-ink">
                {t('home.trace_title')}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <span
                className="w-2 h-2 rounded-full"
                style={{ background: isStreaming ? '#16834A' : '#52685E' }}
                aria-hidden="true"
              />
              <span className="text-xs font-medium" style={{ color: isStreaming ? '#16834A' : '#52685E' }}>
                {isStreaming ? t('misc.live') : t('misc.done')}
              </span>
            </div>
          </div>

          <TraceTimeline events={traceEvents} loading={isStreaming && traceEvents.length === 0} />
          {!isStreaming && traceEvents.length === 0 && (
            <p className="text-xs text-center py-3" style={{ color: '#64748B' }}>
              {t('misc.trace_idle')}
            </p>
          )}
        </div>

        {/* ── Current Plan Preview ─────────────────────────────── */}
        {plan && (
          <div
            className="rounded-2xl p-4 lg:p-5 bg-white border border-sage-mist/80 shadow-card w-full"
          >
            {/* Header */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center bg-sage-mist/70 text-forest"
                >
                  <Sprout className="w-4 h-4" aria-hidden="true" />
                </div>
                <div>
                  <span className="text-sm font-bold block text-ink">
                    {t('home.plan_preview')}
                  </span>
                  <span className="text-[11px] text-muted">
                    {t('misc.plan_preview_hint')}
                  </span>
                </div>
              </div>
              <Link
                to="/dashboard"
                className="text-xs font-semibold hover:underline flex-shrink-0 text-fresh-leaf"
              >
                {t('misc.view_full_plan')} →
              </Link>
            </div>

            {/* Crop cards — 3 horizontal / responsive */}
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
              {((plan.strategies ?? []).find((s) => s.id === plan.recommended_strategy)?.allocations ?? plan.strategies?.[0]?.allocations ?? [])
                .slice(0, 3)
                .map((alloc) => {
                  const crop = (plan.crops ?? []).find((c) => c.crop_id === alloc.crop_id)
                  if (!crop) return null
                  const profitVal = (crop.profit_rs_per_acre?.[selectedScenario] ?? 0) * alloc.acres
                  const waterNeedSv = crop.water_need_m3_per_acre?.[selectedScenario] as unknown
                  const waterVal = typeof waterNeedSv === 'number'
                    ? waterNeedSv
                    : (typeof waterNeedSv === 'object' && waterNeedSv !== null && 'value' in waterNeedSv
                        ? Number((waterNeedSv as { value: number }).value)
                        : 0)
                  const waterM3 = waterVal * alloc.acres
                  const waterLow = (waterM3 * 1000) / 100000 < 2
                  const waterMed = !waterLow && (waterM3 * 1000) / 100000 < 4
                  const waterLabel = waterLow ? 'Low water' : waterMed ? 'Medium water' : 'High water'
                  const waterColor = waterLow ? '#16834A' : waterMed ? '#0ea5e9' : '#f59e0b'

                  return (
                    <div
                      key={alloc.crop_id}
                      className="rounded-xl p-3.5 flex flex-col items-center gap-1.5 transition-shadow hover:shadow-md border border-sage-mist/80 bg-[#FAFFF8]"
                    >
                      {/* Crop illustration */}
                      <div
                        className="w-14 h-14 rounded-xl flex items-center justify-center text-3xl bg-sage-mist/50"
                      >
                        {getCropEmoji(alloc.crop_id)}
                      </div>

                      <p className="text-xs font-bold text-center truncate w-full text-ink">
                        {crop.names?.[lang] ?? crop.crop_id}
                      </p>
                      <p className="text-[10px] text-muted">
                        {alloc.acres} {t('units.acres')}
                      </p>

                      <div className="w-full rounded-lg px-2 py-1 text-center bg-sage-mist/40 border border-sage-mist/60">
                        <p className="text-[10px] font-medium text-muted">
                          Est. Profit
                        </p>
                        <p className="text-xs font-bold text-forest">
                          ₹{Math.round(profitVal || 0).toLocaleString('en-IN')}
                        </p>
                      </div>

                      <div className="flex items-center gap-1 text-[10px] font-medium" style={{ color: waterColor }}>
                        <Droplets className="w-3 h-3" aria-hidden="true" />
                        {waterLabel}
                      </div>
                    </div>
                  )
                })}
            </div>
          </div>
        )}

        {/* ── Performance & Impact Summary ─────────────────────── */}
        {plan && (
          <div
            className="rounded-2xl p-4 lg:p-5 bg-white border border-sage-mist/80 shadow-card w-full"
          >
            {/* Header matching Current Plan Preview */}
            <div className="flex items-center justify-between mb-3.5">
              <div className="flex items-center gap-2">
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center bg-sage-mist/70 text-forest"
                >
                  <BarChart2 className="w-4 h-4" aria-hidden="true" />
                </div>
                <div>
                  <span className="text-sm font-bold block text-ink">
                    Plan Impact & Resource Summary
                  </span>
                  <span className="text-[11px] text-muted">
                    Key economic returns and resource benchmarks vs traditional farming
                  </span>
                </div>
              </div>
              <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-sage-mist/60 text-forest border border-sage-mist capitalize">
                {selectedScenario} Scenario
              </span>
            </div>

            <SummaryTiles plan={plan} scenario={selectedScenario} compact />
          </div>
        )}
      </div>

      {/* Message entry animation */}
      <style>{`
        @keyframes msgIn {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes typingDot {
          0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
          30% { transform: translateY(-5px); opacity: 1; }
        }
      `}</style>
    </div>
  )
}
