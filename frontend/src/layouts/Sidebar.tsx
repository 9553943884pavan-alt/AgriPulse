/**
 * Sidebar — Forest Green (#073B2B) theme.
 * Clean, modern navigation with Fresh Leaf (#16834A) active states
 * and Sunrise Gold (#F3C66B) weather indicators (no photo backgrounds).
 */

import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Home, ClipboardList, BarChart2, GitCompare, Database, Leaf, SunMedium, MapPin } from 'lucide-react'

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
      className="hidden lg:flex flex-col flex-shrink-0 w-64 bg-forest border-r border-[#0d4f3b] text-white select-none z-30"
      aria-label="Main navigation"
    >
      {/* ── Brand Header ────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-5 pt-6 pb-5 flex-shrink-0">
        <div
          className="w-10 h-10 rounded-2xl flex items-center justify-center shadow-md flex-shrink-0 transition-transform hover:scale-105"
          style={{ background: '#16834A' }}
        >
          <Leaf className="w-5 h-5 text-white" strokeWidth={2.4} aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <span className="block text-[19px] font-extrabold tracking-tight text-white leading-tight">
            AgriPulse
          </span>
          <span className="block text-[11px] leading-tight mt-0.5 font-medium text-sage-mist truncate">
            {t('misc.topbar_tagline')}
          </span>
        </div>
      </div>

      {/* ── Navigation Links ────────────────────────────────────── */}
      <nav className="px-3.5 space-y-1.5 overflow-y-auto flex-1 py-2" aria-label="Sidebar navigation">
        {NAV_ITEMS.map(({ to, icon: Icon, key }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 ${
                isActive
                  ? 'bg-fresh-leaf text-white shadow-md'
                  : 'text-white/80 hover:bg-white/10 hover:text-white'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <div
                  className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors ${
                    isActive
                      ? 'bg-white/20 text-white'
                      : 'bg-white/5 border border-white/10 text-sage-mist'
                  }`}
                >
                  <Icon
                    className="w-4 h-4"
                    aria-hidden="true"
                    strokeWidth={isActive ? 2.5 : 2}
                  />
                </div>
                <span className="flex-1 truncate">{t(`nav.${key}`)}</span>
                {isActive && (
                  <span
                    className="w-1.5 h-1.5 rounded-full bg-sunrise-gold shadow-sm flex-shrink-0"
                    aria-hidden="true"
                  />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* ── Weather & Status Card (No Photos, Modern UI) ────────── */}
      <div className="p-3.5 flex-shrink-0">
        <div
          className="rounded-2xl p-3.5 relative overflow-hidden shadow-sm"
          style={{
            background: 'linear-gradient(145deg, #0C4D39 0%, #083829 100%)',
            border: '1px solid rgba(217, 235, 203, 0.15)',
          }}
        >
          {/* Subtle gold ambient glow */}
          <div
            className="absolute -top-6 -right-6 w-20 h-20 rounded-full pointer-events-none opacity-20"
            style={{ background: 'radial-gradient(circle, #F3C66B 0%, transparent 70%)' }}
            aria-hidden="true"
          />

          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <div
                className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 shadow-xs"
                style={{ background: 'rgba(243, 198, 107, 0.15)', border: '1px solid rgba(243, 198, 107, 0.35)' }}
              >
                <SunMedium className="w-4 h-4 text-sunrise-gold" strokeWidth={2.4} aria-hidden="true" />
              </div>
              <div>
                <p className="text-white text-base font-bold leading-none">23°C</p>
                <p className="text-[11px] leading-tight text-sage-mist mt-0.5">Partly Cloudy</p>
              </div>
            </div>
            <span
              className="text-[10px] font-semibold px-2 py-0.5 rounded-full text-forest"
              style={{ background: '#F3C66B' }}
            >
              Live
            </span>
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-white/10 text-[11px]">
            <div className="flex items-center gap-1 text-white/90">
              <MapPin className="w-3 h-3 text-sunrise-gold" />
              <span className="font-medium">Beed, Maharashtra</span>
            </div>
            <span className="text-sage-mist font-normal">Kharif '26</span>
          </div>
        </div>
      </div>
    </aside>
  )
}
