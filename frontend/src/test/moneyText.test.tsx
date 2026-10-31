import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { MoneyText } from '@/components/MoneyText'

describe('MoneyText', () => {
  it('formats 70000 as ₹70,000', () => {
    const { container } = render(<MoneyText value={70000} />)
    expect(container.textContent).toContain('70,000')
  })

  it('formats 100000 with Indian grouping ₹1,00,000', () => {
    const { container } = render(<MoneyText value={100000} />)
    expect(container.textContent).toContain('1,00,000')
  })

  it('hides ₹ when prefix=false', () => {
    const { container } = render(<MoneyText value={5000} prefix={false} />)
    expect(container.textContent).not.toContain('₹')
  })
})
