import { api, API_BASE, ApiError } from './client'
import type { AccessGroup, Health, LoginResult, Me, MfaSetup, SessionRow } from './types'

/** Sets the csrftoken cookie (call once before the first write). */
export const ensureCsrf = () => api.get<void>('/auth/csrf/')

export const login = (username: string, password: string) => api.post<LoginResult>('/auth/login/', { username, password })

export const verifyMfa = (code: string) => api.post<Me>('/auth/mfa/verify/', { code })

export const logout = () => api.post<void>('/auth/logout/')

/** The signed-in user, or null when nobody is signed in. */
export async function me(): Promise<Me | null> {
  try {
    return await api.get<Me>('/auth/me/')
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null
    throw error
  }
}

export const mySessions = () => api.get<SessionRow[]>('/auth/sessions/')

export const revokeAllMySessions = () => api.post<void>('/auth/sessions/revoke-all/')

export const startMfaSetup = () => api.post<MfaSetup>('/auth/mfa/setup/')

export const confirmMfa = (code: string) => api.post<Me>('/auth/mfa/confirm/', { code })

export const changePassword = (old_password: string, new_password: string) =>
  api.post<void>('/auth/password/', { old_password, new_password })

export const myAccessGroups = () => api.get<AccessGroup[]>('/access-groups/mine/')

/** Health is public and answers 503 (same body) when a service is down. */
export async function health(): Promise<Health> {
  const response = await fetch(`${API_BASE}/health/`, { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
  return (await response.json()) as Health
}
