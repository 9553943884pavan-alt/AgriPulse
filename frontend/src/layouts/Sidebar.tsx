/**
 * Sidebar — dark forest-green, 260px.
 * Logo top, nav items with icon boxes, landscape scene bottom with weather widget.
 * Active item: solid #22C55E chip (matches reference exactly).
 */

import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Home, ClipboardList, BarChart2, GitCompare, Database, Leaf } from 'lucide-react'

const NAV_ITEMS = [
  { to: '/',           icon: Home,          key: 'home' },
  { to: '/profile',    icon: ClipboardList, key: 'profile' },
  { to: '/dashboard',  icon: BarChart2,     key: 'dashboard' },
  { to: '/comparison', icon: GitCompare,    key: 'comparison' },
  { to: '/sources',    icon: Database,      key: 'sources' },
] as const

export function Sidebar() {
  const { t } = useTranslation()

  return (
    <aside
      className="hidden lg:flex flex-col flex-shrink-0 overflow-hidden"
      style={{
        width: 260,
        background: 'linear-gradient(180deg, #053d2e 0%, #064e3b 30%, #065f46 70%, #047857 100%)',
      }}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-5 pt-5 pb-4 flex-shrink-0">
        <div className="w-10 h-10 rounded-2xl flex items-center justify-center shadow-lg flex-shrink-0" style={{ background: '#22C55E' }}>
          <Leaf className="w-5 h-5 text-white" strokeWidth={2.5} aria-hidden="true" />
        </div>
        <div>
          <span className="block text-[19px] font-extrabold text-white leading-tight tracking-tight">AgriPulse</span>
          <span className="block text-[10px] leading-tight mt-0.5 font-medium" style={{ color: '#6ee7b7' }}>
            {t('misc.topbar_tagline')}
          </span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="px-3 space-y-1 overflow-y-auto flex-1" aria-label="Main navigation">
        {NAV_ITEMS.map(({ to, icon: Icon, key }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 ${
                isActive ? 'text-white' : 'text-green-100/80 hover:bg-white/10 hover:text-white'
              }`
            }
            style={({ isActive }) => isActive ? { background: '#22C55E' } : {}}
          >
            {({ isActive }) => (
              <>
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                  style={{
                    background: isActive ? 'rgba(255,255,255,0.25)' : 'rgba(255,255,255,0.08)',
                    border: isActive ? 'none' : '1px solid rgba(255,255,255,0.1)',
                  }}
                >
                  <Icon
                    className={`w-4 h-4 ${isActive ? 'text-white' : 'text-green-200'}`}
                    aria-hidden="true"
                    strokeWidth={isActive ? 2.5 : 1.8}
                  />
                </div>
                <span>{t(`nav.${key}`)}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Landscape photo — real countryside scene */}
      <div className="relative overflow-hidden flex-shrink-0" style={{ height: 230 }}>
        {/* Real photo background */}
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: 'url(/sidebar-landscape.jpg)',
            backgroundSize: 'cover',
            backgroundPosition: 'center bottom',
            backgroundRepeat: 'no-repeat',
          }}
          aria-hidden="true"
        />

        {/* Top fade: blend photo into dark green sidebar above */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: 'linear-gradient(to bottom, rgba(6,78,59,0.72) 0%, rgba(6,78,59,0.28) 22%, rgba(0,0,0,0.08) 60%, rgba(0,0,0,0.22) 100%)',
          }}
          aria-hidden="true"
        />

        {/* Weather widget */}
        <div
          className="absolute bottom-3 left-3 right-3 rounded-xl flex items-center gap-2.5 px-3 py-2"
          style={{ background: 'rgba(0,0,0,0.42)', backdropFilter: 'blur(8px)', border: '1px solid rgba(255,255,255,0.1)' }}
        >
          <span className="text-xl flex-shrink-0" aria-hidden="true">🌤️</span>
          <div className="flex-1 min-w-0">
            <p className="text-white text-sm font-bold leading-none">23°C</p>
            <p className="text-[10px] leading-none mt-0.5 font-medium" style={{ color: '#6ee7b7' }}>Partly Cloudy</p>
          </div>
          <div className="flex items-center gap-1 flex-shrink-0">
            <span className="text-[10px]" style={{ color: '#6ee7b7' }}>📍</span>
            <span className="text-[10px] font-medium" style={{ color: '#6ee7b7' }}>Beed, MH</span>
          </div>
        </div>
      </div>
    </aside>
  )
}
