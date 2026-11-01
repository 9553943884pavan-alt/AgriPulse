import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { loadEnv } from 'vite'

// Production build guard: fail if VITE_USE_SAMPLES is set to true.
// This ensures sample/contract data never ships to production.
export default defineConfig(({ mode }) => {
  const useSamples = loadEnv(mode, '.', '').VITE_USE_SAMPLES === 'true'
  if (mode === 'production' && useSamples) {
    throw new Error(
      'VITE_USE_SAMPLES=true is not allowed in a production build. ' +
      'Remove this flag before deploying.'
    )
  }

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': '/src',
      },
    },
    test: {
      globals: true,
      exclude: ['node_modules', 'dist', 'e2e/**'],
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      coverage: {
        provider: 'v8',
      },
    },
  }
})
