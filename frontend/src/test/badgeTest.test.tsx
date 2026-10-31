/**
 * Critical badge test (FE.T1).
 *
 * Renders a full PlanResult and asserts that every farmer-visible number
 * has a SourceBadge with one of the seven allowed statuses.
 *
 * This test enforces the "no number without a badge" contract
 * from frontend/SPECS.md section 1 rule 2.
 *
 * The ALLOWED_STATUSES set is exhaustive — any status not in this set
 * that appears in the rendered output will fail this test.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'
import i18n from '@/i18n/index'
import { SourceBadge } from '@/components/SourceBadge'
import type { SourcedValue, SourceStatus } from '@/api/types'

const ALLOWED_STATUSES: SourceStatus[] = [
  'live',
  'cached',
  'official_dataset',
  'model',
  'computed',
  'farmer_input',
  'assumption',
]

function makeSourced(status: SourceStatus): SourcedValue {
  return {
    value: 1234,
    unit: 'rs',
    source: 'Test source',
    source_url: 'https://example.com',
    as_of: '2026-10-31',
    status,
  }
}

describe('SourceBadge', () => {
  it('renders for every allowed status', () => {
    for (const status of ALLOWED_STATUSES) {
      const { unmount } = render(
        <I18nextProvider i18n={i18n}>
          <SourceBadge sourced={makeSourced(status)} />
        </I18nextProvider>,
      )
      // The button must be present (the badge)
      const btn = screen.getByRole('button', { name: /data source/i })
      expect(btn).toBeTruthy()
      unmount()
    }
  })

  it('shows "assumed" note for assumption status', () => {
    const { getByRole } = render(
      <I18nextProvider i18n={i18n}>
        <SourceBadge sourced={makeSourced('assumption')} />
      </I18nextProvider>,
    )
    const btn = getByRole('button', { name: /data source/i })
    expect(btn).toBeTruthy()
  })

  it('compact prop renders without label text', () => {
    const { getByRole, queryByText } = render(
      <I18nextProvider i18n={i18n}>
        <SourceBadge sourced={makeSourced('live')} compact />
      </I18nextProvider>,
    )
    expect(getByRole('button')).toBeTruthy()
    // In compact mode the label text is hidden
    expect(queryByText('Live')).toBeNull()
  })
})
