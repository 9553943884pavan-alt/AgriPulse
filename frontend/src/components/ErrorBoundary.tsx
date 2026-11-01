import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('AgriPulse ErrorBoundary caught an unhandled error:', error, errorInfo)
  }

  private handleReset = () => {
    try {
      // Clear all agripulse-related keys (cover both old and new key names)
      localStorage.removeItem('agripulse-storage')
      localStorage.removeItem('agripulse-session')
      // Clear any other persisted keys
      Object.keys(localStorage).forEach((key) => {
        if (key.startsWith('agripulse')) localStorage.removeItem(key)
      })
    } catch {
      // ignore
    }
    window.location.href = '/'
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[#F7F8EE] flex flex-col items-center justify-center p-6 text-center">
          <div className="w-16 h-16 rounded-2xl bg-amber-100 flex items-center justify-center text-3xl mb-4 shadow-sm border border-amber-200">
            ⚠️
          </div>
          <h1 className="text-xl font-bold text-gray-900 mb-2">Something went wrong</h1>
          <p className="text-sm text-gray-600 max-w-md mb-6">
            An unexpected error occurred while rendering the farm plan interface. You can reload the page or reset the workspace to recover.
          </p>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-emerald-600 text-white rounded-xl text-sm font-semibold hover:bg-emerald-700 shadow-sm transition"
            >
              Refresh Page
            </button>
            <button
              type="button"
              onClick={this.handleReset}
              className="px-4 py-2 bg-white text-gray-700 border border-gray-300 rounded-xl text-sm font-semibold hover:bg-gray-50 transition"
            >
              Reset Session
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
