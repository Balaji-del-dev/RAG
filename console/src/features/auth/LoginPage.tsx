import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router'
import * as auth from '../../api/auth'
import { useSession } from '../../auth/session'
import { safeNext } from '../../lib/format'
import { loginErrorMessage } from './loginErrors'

export default function LoginPage() {
  const { me, setMe } = useSession()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (me && !me.mfa_required) return <Navigate to={next} replace />

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await auth.ensureCsrf()
      const result = await auth.login(username.trim(), password)
      setMe(result.user)
      navigate(result.mfa_required ? `/login/mfa?next=${encodeURIComponent(next)}` : next, { replace: true })
    } catch (err) {
      setError(loginErrorMessage(err))
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit} noValidate>
        <h1>Sign in</h1>
        <p className="muted">RAG Platform · runs on this machine</p>
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus required />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error && (
          <p className="alert alert-error" role="alert">
            {error}
          </p>
        )}
        <button className="btn btn-primary btn-block" disabled={busy || !username || !password}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
