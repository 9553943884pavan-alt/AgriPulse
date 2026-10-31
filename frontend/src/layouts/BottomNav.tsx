/** Bottom navigation bar — shown on mobile (< lg). */

import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Home, ClipboardList, BarChart2, GitCompare } from 'lucide-react'

const NAV_ITEMS = [
  { to: '/',           icon: Home,          key: 'home' },
  { to: '/profile',    icon: ClipboardList, key: 'profile' },
  { to: '/dashboard',  icon: BarChart2,     key: 'dashboard' },
  { to: '/comparison', icon: GitCompare,    key: 'comparison' },
] as const

export function BottomNav() {
  const { t } = useTranslation()

  return (
    <nav
      className="lg:hidden fixed bottom-0 inset-x-0 bg-white border-t border-gray-100 z-30 safe-area-inset-bottom shadow-[0_-1px_8px_rgba(0,0,0,0.06)]"
      aria-label="Main navigation"
    >
      <div className="flex">
        {NAV_ITEMS.map(({ to, icon: Icon, key }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex-1 flex flex-col items-center gap-1 py-3 text-[11px] font-medium transition-colors
              ${isActive ? 'text-green-700' : 'text-gray-400'}`
            }
          >
            {({ isActive }) => (
              <>
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center transition-all ${isActive ? 'bg-green-50' : ''}`}>
                  <Icon
                    className={`w-5 h-5 ${isActive ? 'text-green-600' : 'text-gray-400'}`}
                    aria-hidden="true"
                  />
                </div>
                <span className="leading-none">{t(`nav.${key}`)}</span>
              </>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
