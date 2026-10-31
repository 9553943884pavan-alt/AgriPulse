/**
 * AppShell — Modern responsive dashboard layout.
 * [Full-height Forest Green Sidebar] | [TopBar + Main Content Area]
 */

import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { TopBar } from './TopBar'
import { Sidebar } from './Sidebar'
import { BottomNav } from './BottomNav'
import { useStore } from '@/state/store'

export function AppShell() {
  const { i18n } = useTranslation()
  const language = useStore((s) => s.language)

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
        <main
          id="main-content"
          className="flex-1 overflow-hidden relative"
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
