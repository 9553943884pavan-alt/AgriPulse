/** Bottom navigation bar — shown on mobile (< lg). */

import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Home, ClipboardList, BarChart2, GitCompare, Database } from 'lucide-react'

const NAV_ITEMS = [
  { to: '/',           icon: Home,          key: 'home' },
  { to: '/profile',    icon: ClipboardList, key: 'profile' },
  { to: '/dashboard',  icon: BarChart2,     key: 'dashboard' },
  { to: '/comparison', icon: GitCompare,    key: 'comparison' },
  { to: '/sources',    icon: Database,      key: 'sources' },
] as const

export function BottomNav() {
  const { t } = useTranslation()

  return (
    <nav
      className="lg:hidden fixed bottom-0 inset-x-0 bg-warm-cream border-t border-sage-mist z-30 safe-area-inset-bottom shadow-[0_-2px_10px_rgba(7,59,43,0.06)]"
      aria-label="Main navigation"
    >
      <div className="flex">
        {NAV_ITEMS.map(({ to, icon: Icon, key }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex-1 flex flex-col items-center gap-1 py-2.5 text-[11px] font-medium transition-colors
              ${isActive ? 'text-forest font-semibold' : 'text-muted'}`
            }
          >
            {({ isActive }) => (
              <>
                <div
                  className={`w-8 h-8 rounded-xl flex items-center justify-center transition-all ${
                    isActive ? 'bg-sage-mist text-forest shadow-xs' : 'text-muted'
                  }`}
                >
                  <Icon
                    className="w-4 h-4"
                    aria-hidden="true"
                    strokeWidth={isActive ? 2.5 : 1.8}
                  />
                </div>
                <span className="leading-none text-[10px]">{t(`nav.${key}`)}</span>
              </>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
