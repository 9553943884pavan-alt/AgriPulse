import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import type { StateStorage } from 'zustand/middleware'
import type {
  FarmProfile,
  PlanResult,
  Language,
  ScenarioId,
  StrategyId,
  TraceEvent,
  ThreadMessage,
} from '@/api/types'

interface AppState {
  // Session
  threadId: string | null
  profile: FarmProfile | null
  plan: PlanResult | null
  messages: ThreadMessage[]
  traceEvents: TraceEvent[]

  // UI preferences
  language: Language
  selectedScenario: ScenarioId
  selectedStrategy: StrategyId | null

  // Actions
  setThreadId: (id: string) => void
  setProfile: (profile: FarmProfile) => void
  setPlan: (plan: PlanResult) => void
  setMessages: (messages: ThreadMessage[]) => void
  addMessage: (msg: ThreadMessage) => void
  addTraceEvent: (event: TraceEvent) => void
  clearTrace: () => void
  setLanguage: (lang: Language) => void
  setScenario: (scenario: ScenarioId) => void
  setStrategy: (strategy: StrategyId) => void
  reset: () => void
}

/** Only the most recent messages are persisted so localStorage stays small. */
export const MAX_PERSISTED_MESSAGES = 50

/** localStorage wrapper that never throws (private mode, quota exceeded, blocked storage). */
const safeStorage: StateStorage = {
  getItem: (name) => {
    try { return localStorage.getItem(name) } catch { return null }
  },
  setItem: (name, value) => {
    try { localStorage.setItem(name, value) } catch { /* persistence is best-effort */ }
  },
  removeItem: (name) => {
    try { localStorage.removeItem(name) } catch { /* persistence is best-effort */ }
  },
}

const initialState = {
  threadId: null,
  profile: null,
  plan: null,
  messages: [],
  traceEvents: [],
  language: 'en' as Language,
  selectedScenario: 'normal' as ScenarioId,
  selectedStrategy: null,
}

export const useStore = create<AppState>()(
  persist(
    (set) => ({
      ...initialState,

      setThreadId: (id) => set({ threadId: id }),
      setProfile: (profile) => set({ profile }),
      setPlan: (plan) => set({
        plan,
        profile: plan.profile,
        threadId: plan.thread_id,
        selectedStrategy: plan.recommended_strategy ?? null,
      }),
      setMessages: (messages) => set({ messages }),
      addMessage: (msg) => set((state) => ({
        messages: [...state.messages, msg],
      })),
      addTraceEvent: (event) => set((state) => {
        const idx = state.traceEvents.findIndex((e) => e.id === event.id)
        if (idx >= 0) {
          const updated = [...state.traceEvents]
          updated[idx] = event
          return { traceEvents: updated }
        }
        return { traceEvents: [...state.traceEvents, event] }
      }),
      clearTrace: () => set({ traceEvents: [] }),
      setLanguage: (language) => set({ language }),
      setScenario: (selectedScenario) => set({ selectedScenario }),
      setStrategy: (selectedStrategy) => set({ selectedStrategy }),
      reset: () => set(initialState),
    }),
    {
      name: 'agripulse-session',
      storage: createJSONStorage(() => safeStorage),
      // Persist plan, profile and preferences so navigation never loses the farm data.
      // Messages ARE persisted (so chat survives reloads) but capped to the last
      // MAX_PERSISTED_MESSAGES entries to keep the stored payload small.
      partialize: (state) => ({
        threadId: state.threadId,
        language: state.language,
        selectedScenario: state.selectedScenario,
        selectedStrategy: state.selectedStrategy,
        profile: state.profile,
        plan: state.plan,
        traceEvents: state.traceEvents,
        messages: state.messages.slice(-MAX_PERSISTED_MESSAGES),
      }),
    },
  ),
)
