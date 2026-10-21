import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, authEvents } from './client'

function respond(status: number, body: unknown) {
  return vi.fn().mockResolvedValue(new Response(body === null ? null : JSON.stringify(body), { status }))
}

describe('apiFetch', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=token-123'
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends X-CSRFToken on writes, using same-origin cookies', async () => {
    const fetchMock = respond(200, { ok: true })
    vi.stubGlobal('fetch', fetchMock)
    await api.post('/thing/', { a: 1 })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/thing/')
    expect(init.credentials).toBe('same-origin')
    expect(new Headers(init.headers).get('X-CSRFToken')).toBe('token-123')
    expect(init.body).toBe('{"a":1}')
  })

  it('does not send the CSRF header on reads', async () => {
    const fetchMock = respond(200, [])
    vi.stubGlobal('fetch', fetchMock)
    await api.get('/thing/')
    expect(new Headers(fetchMock.mock.calls[0][1].headers).has('X-CSRFToken')).toBe(false)
  })

  it('turns the error body into an ApiError with code, message and field errors', async () => {
    vi.stubGlobal(
      'fetch',
      respond(400, { error: { code: 'validation_error', message: 'Some fields are not valid.', details: { email: ['Taken.'] } }, request_id: 'r1' }),
    )
    const error = await api.post('/thing/').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('validation_error')
    expect((error as ApiError).fieldErrors('email')).toEqual(['Taken.'])
    expect((error as ApiError).requestId).toBe('r1')
  })

  it('announces a 401 so the session can be cleared', async () => {
    vi.stubGlobal('fetch', respond(401, { error: { code: 'not_authenticated', message: 'Sign in.' } }))
    const listener = vi.fn()
    authEvents.addEventListener('unauthorized', listener)
    await api.get('/thing/').catch(() => undefined)
    authEvents.removeEventListener('unauthorized', listener)
    expect(listener).toHaveBeenCalledTimes(1)
  })

  it('returns undefined for 204 No Content', async () => {
    vi.stubGlobal('fetch', respond(204, null))
    await expect(api.post('/thing/')).resolves.toBeUndefined()
  })
})
