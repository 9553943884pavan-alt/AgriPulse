import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { FarmProfile, PlanResult, Language, ScenarioId, StrategyId, TraceEvent } from '@/api/types'

interface ThreadMessage {
  role: 'farmer' | 'agent'
  text: string
  language: Language
  at: string
}

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
  addMessage: (msg: ThreadMessage) => void
  addTraceEvent: (event: TraceEvent) => void
  setLanguage: (lang: Language) => void
  setScenario: (scenario: ScenarioId) => void
  setStrategy: (strategy: StrategyId) => void
  reset: () => void
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
        selectedStrategy: plan.recommended_strategy ?? null,
      }),
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
      setLanguage: (language) => set({ language }),
      setScenario: (selectedScenario) => set({ selectedScenario }),
      setStrategy: (selectedStrategy) => set({ selectedStrategy }),
      reset: () => set(initialState),
    }),
    {
      name: 'agripulse-session',
      // Persist plan, profile and preferences so navigation never loses the farm data.
      // Messages are NOT persisted (they can get large and the greeting re-runs fine).
      partialize: (state) => ({
        threadId: state.threadId,
        language: state.language,
        selectedScenario: state.selectedScenario,
        selectedStrategy: state.selectedStrategy,
        profile: state.profile,
        plan: state.plan,
        traceEvents: state.traceEvents,
        messages: state.messages,
      }),
    },
  ),
)
