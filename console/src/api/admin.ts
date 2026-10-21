import { api, type Page } from './client'
import type { AccessGroup, AdminUser, Role, SessionRow } from './types'

export type UserFilters = { search?: string; role?: string; access_group?: string; is_active?: string; locked?: string; page?: number }

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== '') search.set(key, String(value))
  const text = search.toString()
  return text ? `?${text}` : ''
}

export const listUsers = (filters: UserFilters = {}) => api.get<Page<AdminUser>>(`/admin/users/${query(filters)}`)

export type NewUser = {
  username: string
  email: string
  display_name: string
  auth_source: 'LOCAL' | 'LDAP'
  password?: string
  role_ids: string[]
  access_group_ids?: string[]
}

export const createUser = (data: NewUser) => api.post<AdminUser>('/admin/users/', data)

export const updateUser = (id: string, data: Partial<Pick<AdminUser, 'email' | 'display_name' | 'is_active'>>) =>
  api.patch<AdminUser>(`/admin/users/${id}/`, data)

export const setUserRoles = (id: string, ids: string[]) => api.put<AdminUser>(`/admin/users/${id}/roles/`, { ids })

export const setUserAccessGroups = (id: string, ids: string[]) => api.put<AdminUser>(`/admin/users/${id}/access-groups/`, { ids })

export const unlockUser = (id: string) => api.post<AdminUser>(`/admin/users/${id}/unlock/`)

export const resetUserMfa = (id: string) => api.post<AdminUser>(`/admin/users/${id}/reset-mfa/`)

export const listRoles = () => api.get<Role[]>('/admin/roles/')

export const listAccessGroups = () => api.get<AccessGroup[]>('/admin/access-groups/')

export const createAccessGroup = (data: { name: string; description: string }) => api.post<AccessGroup>('/admin/access-groups/', data)

export const updateAccessGroup = (id: string, data: { name?: string; description?: string }) =>
  api.patch<AccessGroup>(`/admin/access-groups/${id}/`, data)

export const deleteAccessGroup = (id: string) => api.delete(`/admin/access-groups/${id}/`)

export const listSessions = (page = 1) => api.get<Page<SessionRow>>(`/admin/sessions/${query({ page })}`)

export const revokeSession = (id: string) => api.post<void>(`/admin/sessions/${id}/revoke/`)
