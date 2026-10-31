/** Card component with Warm Cream / White base and Sage Mist borders. */

interface CardProps {
  children: React.ReactNode
  className?: string
  as?: React.ElementType
}

export function Card({ children, className = '', as: Tag = 'div' }: CardProps) {
  return (
    <Tag className={`bg-white rounded-card shadow-card border border-sage-mist/80 transition-shadow ${className}`}>
      {children}
    </Tag>
  )
}

/** Card header row: icon + title + optional subtitle */
interface CardHeaderProps {
  icon?: React.ReactNode
  title: string
  subtitle?: string
  action?: React.ReactNode
  className?: string
}

export function CardHeader({ icon, title, subtitle, action, className = '' }: CardHeaderProps) {
  return (
    <div className={`flex items-start justify-between gap-3 ${className}`}>
      <div className="flex items-center gap-3">
        {icon && (
          <span className="flex-shrink-0 w-9 h-9 flex items-center justify-center rounded-xl bg-sage-mist/60 text-forest font-semibold">
            {icon}
          </span>
        )}
        <div>
          <h2 className="text-xl font-semibold text-ink leading-tight">{title}</h2>
          {subtitle && <p className="text-sm text-muted mt-0.5">{subtitle}</p>}
        </div>
      </div>
      {action && <div className="flex-shrink-0">{action}</div>}
    </div>
  )
}
