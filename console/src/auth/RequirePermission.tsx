import type { ReactNode } from 'react'
import { NoPermission } from '../components/Feedback'
import { useCan } from './session'

/** Shows children only when the user has the permission. Display only — the server enforces. */
export function RequirePermission({
  perm,
  children,
  fallback,
}: {
  perm: string
  children: ReactNode
  fallback?: ReactNode
}) {
  const can = useCan()
  if (can(perm)) return children
  return fallback === undefined ? <NoPermission perm={perm} /> : fallback
}
