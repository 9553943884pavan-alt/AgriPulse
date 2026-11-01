import '@testing-library/jest-dom'
import { vi } from 'vitest'

// Mock MediaRecorder (not available in jsdom)
Object.defineProperty(globalThis, 'MediaRecorder', {
  configurable: true,
  value: vi.fn().mockImplementation(() => ({
    start: vi.fn(),
    stop: vi.fn(),
    state: 'inactive',
    ondataavailable: null,
    onstop: null,
  })),
})

Object.assign(globalThis.MediaRecorder, {
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
