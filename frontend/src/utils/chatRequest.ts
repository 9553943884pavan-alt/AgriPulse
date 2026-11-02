/** Pure helpers for building the POST /api/agent/chat body. */

import type { ChatRequest, FarmProfile, Language } from '@/api/types'

export const MAX_MESSAGE_LENGTH = 2000

const THREAD_ID_RE = /^th_[0-9a-f]{32}$/

export function isValidThreadId(id: string | null | undefined): id is string {
  return typeof id === 'string' && THREAD_ID_RE.test(id)
}

function hasRealLocation(profile: FarmProfile): boolean {
  const loc = typeof profile.location_text === 'string' ? profile.location_text.trim().toLowerCase() : ''
  return loc !== '' && loc !== 'unknown'
}

/** True for backend placeholder profiles (no real location or no land). Never persist these. */
export function isPlaceholderProfile(profile: FarmProfile | null | undefined): boolean {
  if (!profile) return true
  return !hasRealLocation(profile) || !(Number(profile.land_acres) > 0)
}

/** A saved profile is complete enough to seed a brand-new conversation. */
export function isUsableProfile(profile: FarmProfile | null | undefined): profile is FarmProfile {
  if (!profile || isPlaceholderProfile(profile)) return false
  return Number(profile.budget_rs) > 0
}

export interface ChatRequestInput {
  threadId: string | null
  message: string
  language: Language
  profile: FarmProfile | null
}

/**
 * Builds the chat body. The saved profile is attached only for a brand-new
 * conversation (no valid thread id yet) and only when it is usable.
 */
export function buildChatRequest(input: ChatRequestInput): ChatRequest {
  const message = input.message.trim().slice(0, MAX_MESSAGE_LENGTH)
  const threadId = isValidThreadId(input.threadId) ? input.threadId : null
  const body: ChatRequest = { thread_id: threadId, message, language: input.language }
  if (threadId === null && isUsableProfile(input.profile)) body.profile = input.profile
  return body
}

/** Normalises agent text for duplicate comparison; '' means "skip this bubble". */
export function normalizeAgentText(text: unknown): string {
  return typeof text === 'string' ? text.trim() : ''
}
