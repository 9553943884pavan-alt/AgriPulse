import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import './i18n/index'          // initialise i18next
import './index.css'

import { AppShell } from './layouts/AppShell'
import { ErrorBoundary } from './components/ErrorBoundary'
import { HomePage } from './pages/HomePage'
import { FarmProfilePage } from './pages/FarmProfilePage'
import { DashboardPage } from './pages/DashboardPage'
import { ComparisonPage } from './pages/ComparisonPage'
import { SourcesPage } from './pages/SourcesPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 min default
      retry: 1,
    },
  },
})

const root = document.getElementById('root')
if (!root) throw new Error('Root element not found')

createRoot(root).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route element={<AppShell />}>
              <Route path="/"            element={<HomePage />} />
              <Route path="/profile"     element={<FarmProfilePage />} />
              <Route path="/dashboard"   element={<DashboardPage />} />
              <Route path="/comparison"  element={<ComparisonPage />} />
              <Route path="/sources"     element={<SourcesPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
)
