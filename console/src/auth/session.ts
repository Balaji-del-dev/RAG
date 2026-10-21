import { createContext, useContext } from 'react'
import type { Me } from '../api/types'

export const ME_KEY = ['me'] as const

export type SessionValue = {
  me: Me | null
  loading: boolean
  setMe: (me: Me | null) => void
  signOut: () => Promise<void>
}

export const SessionContext = createContext<SessionValue | null>(null)

export function useSession(): SessionValue {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession must be used inside <SessionProvider>')
  return value
}

/** can('documents.upload') — a display hint only; the server checks every call. */
export function useCan(): (permission: string) => boolean {
  const { me } = useSession()
  return (permission: string) => Boolean(me?.permissions.includes(permission))
}
