import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup()
})

// Minimal router + query-client friendly stubs are provided per-test.
// Silence noisy warnings from recharts/jsdom in CI.
vi.spyOn(console, 'warn').mockImplementation(() => {})
