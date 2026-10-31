/**
 * AppShell — 3-column layout matching the reference image.
 *
 * [Sidebar ~280px] [Chat ~52%] [Right panel ~30%]
 *
 * The entire shell is viewport-height. Each column manages its own scrolling.
 * The TopBar (landscape banner) sits above the 3-column area.
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
    <div className="h-screen flex flex-col overflow-hidden bg-[#F7FAF1]">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main
          id="main-content"
          className="flex-1 overflow-hidden"
          tabIndex={-1}
        >
          <Outlet />
        </main>
      </div>
      <BottomNav />
    </div>
  )
}
