/**
 * Tracks which chat request is current so late events from an aborted or
 * superseded stream can be ignored.
 */

export interface StreamGuard {
  /** Starts a new request and returns its token; all earlier tokens become stale. */
  begin(): number
  /** True only for the most recently started request. */
  isCurrent(token: number): boolean
  /** Invalidates every outstanding token (e.g. on unmount). */
  invalidate(): void
}

export function createStreamGuard(): StreamGuard {
  let current = 0
  return {
    begin: () => {
      current += 1
      return current
    },
    isCurrent: (token) => token === current,
    invalidate: () => {
      current += 1
    },
  }
}
