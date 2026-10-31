/** Button component — primary (Forest Green), secondary, ghost variants. */

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  children: React.ReactNode
}

const VARIANT_CLASSES: Record<NonNullable<ButtonProps['variant']>, string> = {
  primary:   'bg-forest text-white hover:bg-fresh-leaf active:scale-95 shadow-sm font-semibold',
  secondary: 'bg-white text-forest border border-sage-mist hover:bg-sage-mist/40 active:scale-95 font-medium',
  ghost:     'text-forest hover:bg-sage-mist/30 active:scale-95',
  danger:    'bg-danger text-white hover:bg-red-800 active:scale-95',
}

const SIZE_CLASSES: Record<NonNullable<ButtonProps['size']>, string> = {
  sm: 'px-3 py-1.5 text-sm min-h-touch',
  md: 'px-4 py-2 text-sm min-h-touch',
  lg: 'px-6 py-3 text-base min-h-touch',
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  children,
  className = '',
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={`
        inline-flex items-center justify-center gap-2 rounded-btn font-medium
        transition-all duration-150 focus-visible:outline-none focus-visible:ring-2
        focus-visible:ring-fresh-leaf focus-visible:ring-offset-2
        disabled:opacity-50 disabled:cursor-not-allowed
        ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}
      `}
    >
      {loading && (
        <span
          className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin"
          aria-hidden="true"
        />
      )}
      {children}
    </button>
  )
}
