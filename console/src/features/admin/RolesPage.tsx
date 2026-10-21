import { useQuery } from '@tanstack/react-query'
import { listRoles } from '../../api/admin'
import { ErrorMessage, Loading, PageHeader } from '../../components/Feedback'
import { StatusBadge } from '../../components/StatusBadge'
import { PERMISSION_TEXT } from '../../lib/permissions'

/** Read-only: the six roles and what each one may do. Roles are given to people on the Users page. */
export default function RolesPage() {
  const roles = useQuery({ queryKey: ['admin-roles'], queryFn: listRoles })
  return (
    <>
      <PageHeader title="Roles" description="What each role may do. Every account is a User; give people more roles on the Users page. A person's permissions add up." />
      <ErrorMessage error={roles.error} />
      {roles.isPending && <Loading />}
      <div className="grid-2">
        {roles.data?.map((role) => (
          <section className="panel" key={role.id}>
            <h2>
              {role.name} {role.is_system && <StatusBadge label="built-in" tone="neutral" />}
            </h2>
            <p className="muted">{role.description}</p>
            <ul className="checklist">
              {role.permissions.map((perm) => (
                <li key={perm}>
                  {PERMISSION_TEXT[perm] ?? perm} <code className="muted small">{perm}</code>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </>
  )
}
