/**
 * QuintalText — displays yield in quintals.
 * Optionally shows bag count (1 bag = 50 kg = 0.5 quintal).
 */

import { useTranslation } from 'react-i18next'

interface QuintalTextProps {
  quintals: number
  showBags?: boolean
  className?: string
}

export function QuintalText({ quintals, showBags = false, className = '' }: QuintalTextProps) {
  const { t } = useTranslation()
  const bags = Math.round(quintals * 2) // 1 quintal = 2 bags of 50 kg

  return (
    <span className={className}>
      {quintals.toFixed(1)} {t('units.quintals')}
      {showBags && (
        <span className="text-muted ml-1 text-xs">
          / {bags} {t('units.bags')}
        </span>
      )}
    </span>
  )
}
