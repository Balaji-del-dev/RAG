import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { Loading } from '../components/Feedback'
import { useSession } from './session'

/** Not signed in → /login?next=…; password accepted but code missing → /login/mfa. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { me, loading } = useSession()
  const location = useLocation()
  if (loading) return <Loading label="Checking your session…" />
  const next = encodeURIComponent(location.pathname + location.search)
  if (!me) return <Navigate to={`/login?next=${next}`} replace />
  if (me.mfa_required) return <Navigate to={`/login/mfa?next=${next}`} replace />
  return children
}
