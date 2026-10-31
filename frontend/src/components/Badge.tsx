/** General-purpose pill badge / chip. */

interface BadgeProps {
  children: React.ReactNode
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'assumption' | 'muted'
  size?: 'sm' | 'md'
  className?: string
}

const VARIANT_CLASSES: Record<NonNullable<BadgeProps['variant']>, string> = {
  default:    'bg-gray-100 text-ink',
  success:    'bg-primary-soft text-primary',
  warning:    'bg-orange-100 text-drought',
  danger:     'bg-red-100 text-danger',
  info:       'bg-blue-100 text-rain',
  assumption: 'bg-orange-50 text-drought border border-drought/30',
  muted:      'bg-gray-100 text-muted',
}

const SIZE_CLASSES: Record<NonNullable<BadgeProps['size']>, string> = {
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-3 py-1 text-sm',
}

export function Badge({
  children,
  variant = 'default',
  size = 'sm',
  className = '',
}: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full font-medium ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`}
    >
      {children}
    </span>
  )
}
