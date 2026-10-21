import { cleanup, fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderWith } from '../../test/render'
import LoginPage from './LoginPage'

function mockFetch(loginStatus: number, loginBody: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      url.endsWith('/auth/csrf/') ? new Response(null, { status: 204 }) : new Response(JSON.stringify(loginBody), { status: loginStatus }),
    ),
  )
}

async function signIn() {
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'alice' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong-password' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
}

describe('LoginPage', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('shows one generic message for a wrong username or password', async () => {
    mockFetch(400, { error: { code: 'validation_error', message: 'Invalid username or password.', details: {} } })
    renderWith(<LoginPage />, { me: null, path: '/login' })
    await signIn()
    expect((await screen.findByRole('alert')).textContent).toBe('Invalid username or password.')
  })

  it('explains a locked account', async () => {
    mockFetch(423, { error: { code: 'account_locked', message: 'Too many failed sign-ins. Try again in 15 minutes.', details: {} } })
    renderWith(<LoginPage />, { me: null, path: '/login' })
    await signIn()
    expect((await screen.findByRole('alert')).textContent).toContain('Too many failed sign-ins')
  })
})
