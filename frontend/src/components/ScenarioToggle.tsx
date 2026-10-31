/**
 * ScenarioToggle — Normal / Drought / Excess rain chips.
 * Switching updates selectedScenario in the store.
 */

import { useTranslation } from 'react-i18next'
import type { ScenarioId } from '@/api/types'
import { useStore } from '@/state/store'

const SCENARIO_CLASSES: Record<ScenarioId, string> = {
  normal:  'bg-primary text-white',
  drought: 'bg-drought text-white',
  excess:  'bg-rain text-white',
}

const INACTIVE_CLASSES = 'bg-surface text-ink border border-gray-300 hover:bg-gray-50'

interface ScenarioToggleProps {
  scenarios: ScenarioId[]
  onChange?: (scenario: ScenarioId) => void
  className?: string
}

export function ScenarioToggle({ scenarios, onChange, className = '' }: ScenarioToggleProps) {
  const { t } = useTranslation()
  const selectedScenario = useStore((s) => s.selectedScenario)
  const setScenario = useStore((s) => s.setScenario)

  const handleClick = (scenario: ScenarioId) => {
    setScenario(scenario)
    onChange?.(scenario)
  }

  return (
    <div role="group" aria-label="Weather scenario" className={`flex gap-2 flex-wrap ${className}`}>
      {scenarios.map((scenario) => {
        const active = selectedScenario === scenario
        return (
          <button
            key={scenario}
            type="button"
            onClick={() => handleClick(scenario)}
            aria-pressed={active}
            className={`
              px-4 py-2 rounded-btn text-sm font-medium min-h-touch
              transition-all duration-150 focus-visible:outline-none
              focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1
              ${active ? SCENARIO_CLASSES[scenario] : INACTIVE_CLASSES}
            `}
          >
            {t(`scenarios.${scenario}`)}
          </button>
        )
      })}
    </div>
  )
}
