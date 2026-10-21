import { csrfToken } from '../lib/csrf'

export const API_BASE = '/api/v1'

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

export type ErrorBody = {
  error?: { code?: string; message?: string; details?: Record<string, unknown> }
  request_id?: string | null
}

/** Every API error has the same shape: { error: { code, message, details }, request_id }. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>
  readonly requestId: string | null

  constructor(status: number, body: ErrorBody | null) {
    super(body?.error?.message ?? `Request failed (${status})`)
    this.name = 'ApiError'
    this.status = status
    this.code = body?.error?.code ?? 'error'
    this.details = body?.error?.details ?? {}
    this.requestId = body?.request_id ?? null
  }

  /** Messages for one form field (validation errors), or [] when there are none. */
  fieldErrors(field: string): string[] {
    const value = this.details[field]
    return Array.isArray(value) ? value.map(String) : []
  }
}

/** Fires 'unauthorized' on any 401, so the session can be cleared in one place. */
export const authEvents = new EventTarget()

export type Page<T> = { count: number; next: string | null; previous: string | null; results: T[] }

type Options = Omit<RequestInit, 'body'> & { json?: unknown; body?: BodyInit }

export async function apiFetch<T>(path: string, options: Options = {}): Promise<T> {
  const { json, headers: givenHeaders, body: givenBody, ...rest } = options
  const method = (rest.method ?? 'GET').toUpperCase()
  const headers = new Headers(givenHeaders)
  headers.set('Accept', 'application/json')
  let body = givenBody
  if (json !== undefined) {
    headers.set('Content-Type', 'application/json')
    body = JSON.stringify(json)
  }
  if (!SAFE_METHODS.has(method)) {
    const token = csrfToken()
    if (token) headers.set('X-CSRFToken', token)
  }

  const response = await fetch(`${API_BASE}${path}`, { ...rest, method, headers, body, credentials: 'same-origin' })
  if (response.status === 204) return undefined as T
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 401) authEvents.dispatchEvent(new Event('unauthorized'))
    throw new ApiError(response.status, data)
  }
  return data as T
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, json?: unknown) => apiFetch<T>(path, { method: 'POST', json }),
  put: <T>(path: string, json?: unknown) => apiFetch<T>(path, { method: 'PUT', json }),
  patch: <T>(path: string, json?: unknown) => apiFetch<T>(path, { method: 'PATCH', json }),
  delete: <T = void>(path: string) => apiFetch<T>(path, { method: 'DELETE' }),
}

/** A short message for any error, for places that show one line. */
export function errorMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof TypeError) return 'Cannot reach the server. Check that the backend is running.'
  return fallback
}
