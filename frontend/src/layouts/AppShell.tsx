/**
 * AppShell — Modern responsive dashboard layout.
 * [Full-height Forest Green Sidebar] | [TopBar + Main Content Area]
 */

import { useEffect, useRef } from 'react'
import { Outlet } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { TopBar } from './TopBar'
import { Sidebar } from './Sidebar'
import { BottomNav } from './BottomNav'
import { useStore } from '@/state/store'
import { useHealth, useThread } from '@/api/queryHooks'

export function AppShell() {
  const { i18n, t } = useTranslation()
  const language = useStore((s) => s.language)
  const threadId = useStore((s) => s.threadId)
  const setProfile = useStore((s) => s.setProfile)
  const setPlan = useStore((s) => s.setPlan)
  const setMessages = useStore((s) => s.setMessages)
  const initialThreadId = useRef(threadId).current
  const thread = useThread(initialThreadId)
  const health = useHealth()

  useEffect(() => {
    if (!thread.data) return
    if (thread.data.profile) setProfile(thread.data.profile)
    if (thread.data.plan) setPlan(thread.data.plan)
    setMessages(thread.data.messages)
  }, [thread.data, setProfile, setPlan, setMessages])

  useEffect(() => {
    if (i18n.language !== language) {
      void i18n.changeLanguage(language)
    }
    document.documentElement.lang = language
  }, [language, i18n])

  return (
    <div className="h-screen flex overflow-hidden bg-page text-ink antialiased">
      {/* Full-height Desktop Sidebar */}
      <Sidebar />

      {/* Main Column */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <TopBar />
        {(health.isError || (health.data && (health.data.status !== 'ok' || !health.data.models_loaded))) && (
          <div
            role="status"
            className="flex items-center justify-between gap-3 px-4 py-2 text-sm bg-amber-50 text-amber-900 border-b border-amber-200"
          >
            <span>{t('errors.backend_not_ready', 'Backend is starting or unavailable. Some planning features may not work yet.')}</span>
            <button type="button" onClick={() => void health.refetch()} className="font-semibold underline">
              {t('errors.retry', 'Retry')}
            </button>
          </div>
        )}
        {thread.isError && (
          <div
            role="alert"
            className="flex items-center justify-between gap-3 px-4 py-2 text-sm bg-red-50 text-red-800 border-b border-red-200"
          >
            <span>{t('errors.thread_restore', 'Could not restore the saved conversation.')}</span>
            <button type="button" onClick={() => void thread.refetch()} className="font-semibold underline">
              {t('errors.retry', 'Retry')}
            </button>
          </div>
        )}
        <main
          id="main-content"
          className="flex-1 overflow-hidden relative pb-[68px] lg:pb-0"
          tabIndex={-1}
        >
          <Outlet />
        </main>
      </div>

      {/* Mobile Bottom Navigation */}
      <BottomNav />
    </div>
  )
}
