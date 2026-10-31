/**
 * WaterText — displays water in litres AND tanker loads.
 * 1 tanker = 10 m³ = 10,000 litres.
 * Input is in m³.
 */

import { useTranslation } from 'react-i18next'

const LITRES_PER_M3 = 1000
const LITRES_PER_TANKER = 10_000

interface WaterTextProps {
  m3: number
  showTankers?: boolean
  className?: string
}

export function WaterText({ m3, showTankers = true, className = '' }: WaterTextProps) {
  const { t } = useTranslation()
  const litres = m3 * LITRES_PER_M3
  const tankers = litres / LITRES_PER_TANKER

  const litreFmt = new Intl.NumberFormat('en-IN').format(litres)
  const tankerFmt = tankers >= 1 ? tankers.toFixed(1) : tankers.toFixed(2)

  return (
    <span className={className}>
      {litreFmt} {t('units.litres')}
      {showTankers && (
        <span className="text-muted ml-1 text-xs">
          / {tankerFmt} {t('units.tanker')}
        </span>
      )}
    </span>
  )
}
