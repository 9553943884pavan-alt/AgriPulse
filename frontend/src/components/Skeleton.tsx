/** Animated skeleton placeholder for loading states. */

interface SkeletonProps {
  className?: string
  /** Pulse animation (default true) */
  animate?: boolean
}

export function Skeleton({ className = '', animate = true }: SkeletonProps) {
  return (
    <div
      role="status"
      aria-label="Loading…"
      className={`bg-gray-200 rounded ${animate ? 'animate-pulse' : ''} ${className}`}
    />
  )
}

/** A skeleton tile matching SummaryTile dimensions */
export function SummaryTileSkeleton() {
  return (
    <div className="bg-surface rounded-card shadow-card p-5 flex items-start gap-4">
      <Skeleton className="w-12 h-12 rounded-full flex-shrink-0" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-7 w-32" />
        <Skeleton className="h-3 w-16" />
      </div>
    </div>
  )
}

/** A skeleton card for crop cards */
export function CropCardSkeleton() {
  return (
    <div className="bg-surface rounded-card shadow-card p-5 space-y-3">
      <div className="flex items-center gap-3">
        <Skeleton className="w-16 h-16 rounded-xl flex-shrink-0" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-3 w-16" />
        </div>
      </div>
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-3/4" />
      <Skeleton className="h-3 w-1/2" />
    </div>
  )
}

/** Skeleton rows for the trace timeline */
export function TraceRowSkeleton() {
  return (
    <div className="flex items-center gap-3 py-2">
      <Skeleton className="w-5 h-5 rounded-full flex-shrink-0" />
      <div className="flex-1 space-y-1">
        <Skeleton className="h-3 w-32" />
        <Skeleton className="h-2 w-20" />
      </div>
      <Skeleton className="h-3 w-10" />
    </div>
  )
}
