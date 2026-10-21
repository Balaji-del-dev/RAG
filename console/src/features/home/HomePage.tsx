import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import * as auth from '../../api/auth'
import { useSession } from '../../auth/session'
import { Loading, PageHeader } from '../../components/Feedback'
import { StatusBadge } from '../../components/StatusBadge'
import { PERMISSION_TEXT } from '../../lib/permissions'
import { visibleNav } from '../../nav'

const SERVICE_NAMES: Record<string, string> = {
  postgres: 'PostgreSQL',
  redis: 'Redis',
  minio: 'MinIO',
  qdrant: 'Qdrant',
  opensearch: 'OpenSearch',
  ollama: 'Ollama',
}

export default function HomePage() {
  const { me } = useSession()
  const health = useQuery({ queryKey: ['health'], queryFn: auth.health, refetchInterval: 30_000 })
  if (!me) return null

  return (
    <>
      <PageHeader title={`Welcome, ${me.display_name || me.username}`} description="What you can do on this platform." />
      <nav className="quick-links" aria-label="Your pages">
        {visibleNav(me.permissions)
          .filter((item) => item.to !== '/')
          .map((item) => (
            <Link key={item.to} to={item.to} className="quick-link">
              {item.label}
            </Link>
          ))}
      </nav>
      <div className="grid-2">
        <section className="panel">
          <h2>Your roles</h2>
          <p>
            {me.roles.map((role) => (
              <StatusBadge key={role} label={role} tone="info" />
            ))}
          </p>
          <h3>You may</h3>
          <ul className="checklist">
            {me.permissions.map((perm) => (
              <li key={perm}>{PERMISSION_TEXT[perm] ?? perm}</li>
            ))}
          </ul>
          <h3>Your access groups</h3>
          <p>{me.access_groups.length ? me.access_groups.join(' · ') : 'None yet — ask an Admin to add you to a group.'}</p>
        </section>
        <section className="panel">
          <h2>Services on this machine</h2>
          {health.isPending && <Loading />}
          {health.data && (
            <ul className="service-list">
              {Object.entries(SERVICE_NAMES).map(([key, name]) => {
                const state = health.data.services[key]
                return (
                  <li key={key}>
                    <span>{name}</span>
                    <StatusBadge label={state ?? 'unknown'} tone={state === 'up' ? 'ok' : state === 'down' ? 'bad' : 'neutral'} />
                  </li>
                )
              })}
            </ul>
          )}
          {health.isError && <p className="alert alert-error">Cannot reach the backend.</p>}
        </section>
      </div>
    </>
  )
}
