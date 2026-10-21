import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { ApiError, errorMessage } from '../api/client'
import { useSession } from '../auth/session'
import { rolesGranting } from '../lib/permissions'

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <p className="muted" role="status" aria-live="polite">
      {label}
    </p>
  )
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>
}

/** Explains which role opens a page, and where it is granted. */
export function NoPermission({ perm }: { perm?: string }) {
  const { me } = useSession()
  const roles = perm ? rolesGranting(perm) : []
  const isAdmin = me?.permissions.includes('accounts.manage')
  return (
    <section className="panel">
      <h1>You don't have permission for this</h1>
      {roles.length > 0 && (
        <p>
          {roles.length === 1 ? 'This page needs the role ' : 'This page needs one of these roles: '}
          <strong>{roles.join(', ')}</strong> (permission <code>{perm}</code>).
        </p>
      )}
      {isAdmin ? (
        <p className="muted">
          You are an Admin: add the role to your own account (or someone else's) on the <Link to="/admin/users">Users</Link> page.
        </p>
      ) : (
        <p className="muted">Ask an Admin to add the role to your account.</p>
      )}
    </section>
  )
}

/** One line for an API error; links to MFA setup when an admin page needs it. */
export function ErrorMessage({ error }: { error: unknown }) {
  const { me } = useSession()
  if (!error) return null
  if (error instanceof ApiError && error.code === 'mfa_required') {
    // The layout already shows this banner to admins who have not set up MFA.
    if (me?.mfa_setup_required) return null
    return (
      <p className="alert alert-warn" role="alert">
        {error.message} <Link to="/account#mfa">Set up your authenticator app</Link>
      </p>
    )
  }
  return (
    <p className="alert alert-error" role="alert">
      {errorMessage(error)}
    </p>
  )
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {description && <p className="muted">{description}</p>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </header>
  )
}
