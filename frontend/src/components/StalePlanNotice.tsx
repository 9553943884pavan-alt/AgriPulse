import { Info } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '@/state/store'
import { isPlanStale } from '@/utils/planStale'

/** Non-blocking notice shown when the saved farm profile differs from the one the plan was built for. */
export function StalePlanNotice() {
  const { t } = useTranslation()
  const plan = useStore((s) => s.plan)
  const profile = useStore((s) => s.profile)
  if (!plan || !isPlanStale(plan.profile, profile)) return null
  return (
    <div
      role="status"
      data-testid="stale-plan-notice"
      className="flex items-start gap-2 rounded-xl px-4 py-3 text-sm border border-amber-200 bg-amber-50 text-amber-900"
    >
      <Info className="w-4 h-4 mt-0.5 flex-shrink-0" aria-hidden="true" />
      <span>{t('misc.plan_stale_notice')}</span>
    </div>
  )
}
