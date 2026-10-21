import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router'
import * as auth from '../../api/auth'
import { ApiError, errorMessage } from '../../api/client'
import { useSession } from '../../auth/session'
import { safeNext } from '../../lib/format'

export default function MfaPage() {
  const { me, setMe, signOut } = useSession()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (!me) return <Navigate to="/login" replace />
  if (!me.mfa_required) return <Navigate to={next} replace />

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      setMe(await auth.verifyMfa(code))
      navigate(next, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? (err.fieldErrors('code')[0] ?? err.message) : errorMessage(err))
      setCode('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit} noValidate>
        <h1>Enter your code</h1>
        <p className="muted">Open your authenticator app and type the 6-digit code for RAG Platform.</p>
        <label>
          Code
          <input
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            inputMode="numeric"
            autoComplete="one-time-code"
            autoFocus
            pattern="\d{6}"
          />
        </label>
        {error && (
          <p className="alert alert-error" role="alert">
            {error}
          </p>
        )}
        <button className="btn btn-primary btn-block" disabled={busy || code.length !== 6}>
          {busy ? 'Checking…' : 'Continue'}
        </button>
        <button
          type="button"
          className="btn btn-link"
          onClick={async () => {
            await signOut()
            navigate('/login', { replace: true })
          }}
        >
          Use a different account
        </button>
      </form>
    </div>
  )
}
