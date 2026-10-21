import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, type ReactNode } from 'react'
import * as auth from '../api/auth'
import { authEvents } from '../api/client'
import type { Me } from '../api/types'
import { ME_KEY, SessionContext, type SessionValue } from './session'

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const meQuery = useQuery({ queryKey: ME_KEY, queryFn: auth.me, staleTime: 60_000, retry: false })

  useEffect(() => {
    auth.ensureCsrf().catch(() => undefined)
  }, [])

  // Any 401 from any call: forget the user and every cached response.
  useEffect(() => {
    const onUnauthorized = () => {
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== ME_KEY[0] })
      queryClient.setQueryData(ME_KEY, null)
    }
    authEvents.addEventListener('unauthorized', onUnauthorized)
    return () => authEvents.removeEventListener('unauthorized', onUnauthorized)
  }, [queryClient])

  const value = useMemo<SessionValue>(
    () => ({
      me: meQuery.data ?? null,
      loading: meQuery.isPending,
      setMe: (me: Me | null) => queryClient.setQueryData(ME_KEY, me),
      signOut: async () => {
        try {
          await auth.logout()
        } finally {
          queryClient.clear()
          queryClient.setQueryData(ME_KEY, null)
        }
      },
    }),
    [meQuery.data, meQuery.isPending, queryClient],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}
