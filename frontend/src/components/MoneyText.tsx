/**
 * MoneyText — formats a number in Indian grouping with ₹ prefix.
 * 70000 → ₹70,000
 * 100000 → ₹1,00,000
 *
 * Never shows a bare number for farmer-visible amounts.
 */

interface MoneyTextProps {
  value: number
  /** Show the ₹ prefix (default true) */
  prefix?: boolean
  className?: string
}

const formatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
})

export function MoneyText({ value, prefix = true, className = '' }: MoneyTextProps) {
  const formatted = formatter.format(value)
  // Intl gives "₹" prefix already; we can strip it for prefix=false
  const display = prefix ? formatted : formatted.replace('₹', '').trim()
  return (
    <span className={`font-tabular-nums ${className}`} aria-label={`${value} rupees`}>
      {display}
    </span>
  )
}
