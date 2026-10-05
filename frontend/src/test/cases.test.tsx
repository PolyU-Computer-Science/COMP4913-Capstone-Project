import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import type { Case } from '@/lib/types'

const mocks = vi.hoisted(() => ({
  fetchCases: vi.fn(),
  fetchMailboxes: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  fetchCases: mocks.fetchCases,
  fetchMailboxes: mocks.fetchMailboxes,
}))

import Cases from '@/pages/cases'

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

const MAILBOXES = [
  { id: 1, name: 'Support' },
  { id: 2, name: 'Sales' },
]

const CASES = [
  {
    id: 'abcdef1234567890',
    mailbox_id: 1,
    email: {
      id: 'abcdef1234567890',
      sender: 'cust@example.com',
      subject: 'Password reset request',
      body: '',
      timestamp: '2026-10-01T10:00:00Z',
      status: 'processed',
    },
    classification: {
      category: 'question',
      topic: 'password_reset',
      priority: 'high',
      summary: '',
      custom: {},
      topic_id: 3,
      topic_raw: 'password_reset',
    },
    draft: 'Hi, ...',
    created_at: '2026-10-01T10:05:00Z',
    sent_at: null,
  },
] as unknown as Case[]

describe('Cases page', () => {
  beforeEach(() => {
    mocks.fetchMailboxes.mockResolvedValue(MAILBOXES)
    mocks.fetchCases.mockResolvedValue(CASES)
  })

  it('renders the mailbox name (not the subject) in the Mailbox column', async () => {
    renderWithProviders(<Cases />)

    const rows = await screen.findAllByRole('row')
    const dataRow = rows[1]
    expect(within(dataRow).getByText('Password reset request')).toBeInTheDocument()
    const cells = within(dataRow).getAllByRole('cell')
    // Column layout: Case | Subject | Mailbox | Category | Topic | Priority | Status | Updated | actions
    expect(cells[2]).toHaveTextContent('Support')
    expect(cells[2].textContent).not.toBe('Password reset request')
  })

  it('shows the subject in its own Subject column', async () => {
    renderWithProviders(<Cases />)

    const rows = await screen.findAllByRole('row')
    const dataRow = rows[1]
    const cells = within(dataRow).getAllByRole('cell')
    expect(cells[1]).toHaveTextContent('Password reset request')
  })

  it('renders an em dash when the case has no mailbox', async () => {
    mocks.fetchCases.mockResolvedValue([
      { ...CASES[0], mailbox_id: null },
    ] as unknown as Case[])
    renderWithProviders(<Cases />)

    const rows = await screen.findAllByRole('row')
    const cells = within(rows[1]).getAllByRole('cell')
    expect(cells[2]).toHaveTextContent('—')
  })
})
