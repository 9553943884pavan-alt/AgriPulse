import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Production build guard: fail if VITE_USE_SAMPLES is set to true.
// This ensures sample/contract data never ships to production.
const useSamples = process.env.VITE_USE_SAMPLES === 'true'
if (process.env.NODE_ENV === 'production' && useSamples) {
  throw new Error(
    'VITE_USE_SAMPLES=true is not allowed in a production build. ' +
    'Remove this flag before deploying.'
  )
}

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': '/src',
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
    },
  },
})
