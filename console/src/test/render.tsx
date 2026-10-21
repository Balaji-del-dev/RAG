import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import type { Me } from '../api/types'
import { SessionContext, type SessionValue } from '../auth/session'

export const baseMe: Me = {
  id: 'u1',
  username: 'alice',
  email: 'alice@example.org',
  display_name: 'Alice',
  auth_source: 'LOCAL',
  mfa_enabled: false,
  roles: ['User'],
  permissions: ['rag.ask', 'documents.view', 'feedback.create'],
  access_groups: ['general'],
  mfa_required: false,
  mfa_setup_required: false,
}

/** Render with a router, a fresh query client and a fixed session. */
export function renderWith(ui: ReactNode, { me = baseMe, path = '/', session = {} }: { me?: Me | null; path?: string; session?: Partial<SessionValue> } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const value: SessionValue = { me, loading: false, setMe: () => undefined, signOut: async () => undefined, ...session }
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <SessionContext.Provider value={value}>{ui}</SessionContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
