/**
 * TopBar — Clean modern navigation header (no photos).
 * Uses Warm Cream (#F7F8EE) base with Sage Mist (#D9EBCB) borders
 * and Forest Green / Sunrise Gold accents.
 */

import { useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LanguagePicker } from '@/components/LanguagePicker'
import { Sparkles, Leaf } from 'lucide-react'
import { useHealth, useSourcesHealth } from '@/api/queryHooks'
import { aiStatus, dataStatus, BADGE_DOT } from '@/utils/topBarStatus'

export function TopBar() {
  const { t } = useTranslation()
  const location = useLocation()
  const health = useHealth()
  const sourcesHealth = useSourcesHealth()
  const dataState = dataStatus(sourcesHealth)
  const aiState = aiStatus(health)
  const dataLabel = t(`topbar.data_${dataState === 'ok' ? 'ok' : dataState}`)
  const aiLabel = t(`topbar.ai_${{ checking: 'checking', ok: 'online', degraded: 'starting', down: 'offline' }[aiState]}`)

  // Derive current view title for breadcrumb
  const getPageTitle = () => {
    switch (location.pathname) {
      case '/':
        return t('nav.home')
      case '/profile':
        return t('nav.profile')
      case '/dashboard':
        return t('nav.dashboard')
      case '/comparison':
        return t('nav.comparison')
      case '/sources':
        return t('nav.sources')
      default:
        return 'AgriPulse'
    }
  }

  return (
    <header className="h-16 flex-shrink-0 z-20 bg-warm-cream border-b border-sage-mist px-4 lg:px-6 flex items-center justify-between">
      {/* ── Left Context ────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        {/* Mobile-only brand */}
        <div className="lg:hidden flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-forest flex items-center justify-center shadow-xs">
            <Leaf className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-forest text-base">AgriPulse</span>
        </div>

        {/* Desktop breadcrumb & status */}
        <div className="hidden lg:flex items-center gap-2.5">
          <span className="text-sm font-semibold text-forest bg-sage-mist/60 px-3 py-1 rounded-full border border-sage-mist">
            {getPageTitle()}
          </span>
          <span className="text-muted text-xs">•</span>
          <div className="flex items-center gap-1.5 text-xs text-muted font-medium">
            <span className={`w-2 h-2 rounded-full ${BADGE_DOT[dataState]}`} aria-hidden="true" />
            <span role="status">{dataLabel}</span>
          </div>
        </div>
      </div>

      {/* ── Right Controls ──────────────────────────────────────── */}
      <div className="flex items-center gap-2.5">
        {/* Real-time AI Badge */}
        <div className="hidden sm:flex items-center gap-1.5 px-3 py-1 rounded-full bg-white border border-sage-mist text-xs font-medium text-forest shadow-xs">
          <Sparkles className="w-3.5 h-3.5 text-sunrise-gold" aria-hidden="true" />
          <span className={`w-2 h-2 rounded-full ${BADGE_DOT[aiState]}`} aria-hidden="true" />
          <span role="status">{aiLabel}</span>
        </div>

        {/* Language selector */}
        <div className="flex items-center">
          <LanguagePicker />
        </div>
      </div>
    </header>
  )
}
