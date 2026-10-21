import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { useSession } from '../auth/session'
import { visibleNav } from '../nav'
import { ErrorBoundary } from './ErrorBoundary'

export function Layout() {
  const { me, signOut } = useSession()
  const navigate = useNavigate()
  const location = useLocation()
  if (!me) return null
  const items = visibleNav(me.permissions)
  const main = items.filter((item) => item.section === 'main')
  const admin = items.filter((item) => item.section === 'admin')

  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand">
          RAG Platform
        </Link>
        <div className="user-menu">
          <Link to="/account" className="user-name">
            {me.display_name || me.username}
          </Link>
          <button
            type="button"
            className="btn btn-small"
            onClick={async () => {
              await signOut()
              navigate('/login', { replace: true })
            }}
          >
            Sign out
          </button>
        </div>
      </header>

      <nav className="sidebar" aria-label="Main">
        <ul>
          {main.map((item) => (
            <li key={item.to}>
              <NavLink to={item.to} end>
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
        {admin.length > 0 && (
          <>
            <p className="nav-section">Administration</p>
            <ul>
              {admin.map((item) => (
                <li key={item.to}>
                  <NavLink to={item.to}>{item.label}</NavLink>
                </li>
              ))}
            </ul>
          </>
        )}
      </nav>

      <main className="content">
        {me.mfa_setup_required && (
          <p className="alert alert-warn" role="status">
            Admin pages need multi-factor sign-in. <Link to="/account#mfa">Set up your authenticator app</Link>.
          </p>
        )}
        {/* keyed by path: moving to another page clears a crash */}
        <ErrorBoundary key={location.pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  )
}
