import '@testing-library/jest-dom'
import { vi } from 'vitest'

// Mock MediaRecorder (not available in jsdom)
global.MediaRecorder = vi.fn().mockImplementation(() => ({
  start: vi.fn(),
  stop: vi.fn(),
  state: 'inactive',
  ondataavailable: null,
  onstop: null,
})) as unknown as typeof MediaRecorder

Object.assign(global.MediaRecorder, {
  isTypeSupported: vi.fn().mockReturnValue(true),
})

// Mock matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})
