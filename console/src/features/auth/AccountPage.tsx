import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import * as auth from '../../api/auth'
import { ApiError } from '../../api/client'
import type { MfaSetup } from '../../api/types'
import { useSession } from '../../auth/session'
import { ConfirmButton } from '../../components/ConfirmButton'
import { ErrorMessage, Loading, PageHeader } from '../../components/Feedback'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime, shortUserAgent } from '../../lib/format'

export default function AccountPage() {
  const { me } = useSession()
  if (!me) return null
  return (
    <>
      <PageHeader title="My account" description="Your profile, sign-in security and active sessions." />
      <section className="panel">
        <h2>Profile</h2>
        <dl className="facts">
          <dt>Username</dt>
          <dd>{me.username}</dd>
          <dt>Name</dt>
          <dd>{me.display_name || '—'}</dd>
          <dt>Email</dt>
          <dd>{me.email}</dd>
          <dt>Roles</dt>
          <dd>{me.roles.join(' · ')}</dd>
          <dt>Access groups</dt>
          <dd>{me.access_groups.length ? me.access_groups.join(' · ') : 'none — you will not see any documents'}</dd>
        </dl>
      </section>
      <MfaSection />
      {me.auth_source === 'LOCAL' && <PasswordSection />}
      <SessionsSection />
    </>
  )
}

function MfaSection() {
  const { me, setMe } = useSession()
  const [setup, setSetup] = useState<MfaSetup | null>(null)
  const [code, setCode] = useState('')
  const start = useMutation({ mutationFn: auth.startMfaSetup, onSuccess: setSetup })
  const confirm = useMutation({
    mutationFn: () => auth.confirmMfa(code),
    onSuccess: (updated) => {
      setMe(updated)
      setSetup(null)
      setCode('')
    },
  })
  if (!me) return null

  return (
    <section className="panel" id="mfa">
      <h2>Authenticator app (multi-factor sign-in)</h2>
      {me.mfa_enabled ? (
        <p>
          <StatusBadge label="On" tone="ok" /> You enter a 6-digit code from your app each time you sign in.
        </p>
      ) : (
        <p>
          <StatusBadge label="Off" tone={me.mfa_setup_required ? 'warn' : 'neutral'} />{' '}
          {me.mfa_setup_required ? 'Admins must turn this on before admin pages open.' : 'Recommended for every account.'}
        </p>
      )}
      {!setup && (
        <button type="button" className="btn" onClick={() => start.mutate()} disabled={start.isPending}>
          {me.mfa_enabled ? 'Move to a new phone' : 'Set up authenticator app'}
        </button>
      )}
      <ErrorMessage error={start.error} />
      {setup && (
        <form
          className="mfa-setup"
          onSubmit={(event: FormEvent) => {
            event.preventDefault()
            confirm.mutate()
          }}
        >
          <ol>
            <li>Open an authenticator app on your phone (for example Google Authenticator, Microsoft Authenticator or Aegis).</li>
            <li>Scan this QR code.</li>
            <li>Type the 6-digit code the app shows.</li>
          </ol>
          <img className="qr" alt="QR code for your authenticator app" src={`data:image/svg+xml;utf8,${encodeURIComponent(setup.qr_svg)}`} />
          <details>
            <summary>Can't scan? Show the setup key</summary>
            <code className="wrap">{setup.otpauth_url}</code>
          </details>
          <label>
            Code from the app
            <input
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              inputMode="numeric"
              autoComplete="one-time-code"
            />
          </label>
          {confirm.error instanceof ApiError && <p className="alert alert-error">{confirm.error.fieldErrors('code')[0] ?? confirm.error.message}</p>}
          <div className="actions">
            <button type="button" className="btn" onClick={() => setSetup(null)}>
              Cancel
            </button>
            <button className="btn btn-primary" disabled={code.length !== 6 || confirm.isPending}>
              Turn on
            </button>
          </div>
        </form>
      )}
    </section>
  )
}

function PasswordSection() {
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [again, setAgain] = useState('')
  const change = useMutation({
    mutationFn: () => auth.changePassword(oldPassword, newPassword),
    onSuccess: () => {
      setOldPassword('')
      setNewPassword('')
      setAgain('')
    },
  })
  const error = change.error instanceof ApiError ? change.error : null
  const mismatch = again.length > 0 && again !== newPassword

  return (
    <section className="panel">
      <h2>Change password</h2>
      <form
        className="form-grid"
        onSubmit={(event: FormEvent) => {
          event.preventDefault()
          change.mutate()
        }}
      >
        <label>
          Current password
          <input type="password" value={oldPassword} onChange={(e) => setOldPassword(e.target.value)} autoComplete="current-password" />
          {error?.fieldErrors('old_password').map((m) => <span className="field-error" key={m}>{m}</span>)}
        </label>
        <label>
          New password (at least 12 characters)
          <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} autoComplete="new-password" />
          {error?.fieldErrors('new_password').map((m) => <span className="field-error" key={m}>{m}</span>)}
        </label>
        <label>
          New password again
          <input type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" />
          {mismatch && <span className="field-error">The passwords do not match.</span>}
        </label>
        {change.isSuccess && <p className="alert alert-ok">Password changed. Your other sessions were signed out.</p>}
        {error && error.code !== 'validation_error' && <p className="alert alert-error">{error.message}</p>}
        <div className="actions">
          <button className="btn btn-primary" disabled={!oldPassword || newPassword.length < 12 || mismatch || change.isPending}>
            Change password
          </button>
        </div>
      </form>
    </section>
  )
}

function SessionsSection() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const sessions = useQuery({ queryKey: ['my-sessions'], queryFn: auth.mySessions })
  const revokeAll = useMutation({
    mutationFn: auth.revokeAllMySessions,
    onSuccess: () => {
      queryClient.clear()
      queryClient.setQueryData(['me'], null)
      navigate('/login', { replace: true })
    },
  })

  return (
    <section className="panel">
      <h2>Where you're signed in</h2>
      {sessions.isPending && <Loading />}
      <ErrorMessage error={sessions.error ?? revokeAll.error} />
      {sessions.data && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Device</th>
                <th>IP address</th>
                <th>Signed in</th>
                <th>Last active</th>
              </tr>
            </thead>
            <tbody>
              {sessions.data.map((row) => (
                <tr key={row.id}>
                  <td>
                    {shortUserAgent(row.user_agent)} {row.is_current && <StatusBadge label="This browser" tone="info" />}
                  </td>
                  <td>{row.ip_address ?? '—'}</td>
                  <td>{formatDateTime(row.created_at)}</td>
                  <td>{formatDateTime(row.last_seen_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="actions">
        <ConfirmButton
          label="Sign out everywhere"
          title="Sign out everywhere?"
          message="Every session of your account ends, including this one. You will need to sign in again."
          danger
          onConfirm={() => revokeAll.mutate()}
        />
      </div>
    </section>
  )
}
