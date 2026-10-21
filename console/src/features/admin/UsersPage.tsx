import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import * as admin from '../../api/admin'
import { ApiError } from '../../api/client'
import type { AccessGroup, AdminUser, Role } from '../../api/types'
import { ConfirmButton } from '../../components/ConfirmButton'
import { EmptyState, ErrorMessage, Loading, PageHeader } from '../../components/Feedback'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../lib/format'

const USER_ROLE = 'User'

function userStatus(user: AdminUser) {
  if (!user.is_active) return <StatusBadge label="Disabled" tone="neutral" />
  if (user.is_locked) return <StatusBadge label="Locked" tone="bad" />
  return <StatusBadge label="Active" tone="ok" />
}

export default function UsersPage() {
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState<admin.UserFilters>({ page: 1 })
  const [editing, setEditing] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const users = useQuery({ queryKey: ['admin-users', filters], queryFn: () => admin.listUsers(filters), placeholderData: keepPreviousData })
  const roles = useQuery({ queryKey: ['admin-roles'], queryFn: admin.listRoles })
  const groups = useQuery({ queryKey: ['admin-access-groups'], queryFn: admin.listAccessGroups })
  const page = filters.page ?? 1
  const selected = users.data?.results.find((u) => u.id === editing) ?? null

  return (
    <>
      <PageHeader
        title="Users"
        description="Create accounts, choose roles and access groups, unlock accounts."
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
            New user
          </button>
        }
      />
      <ErrorMessage error={users.error ?? roles.error ?? groups.error} />

      {creating && roles.data && groups.data && (
        <NewUserForm roles={roles.data} groups={groups.data} onDone={() => setCreating(false)} />
      )}

      <form
        className="toolbar"
        onSubmit={(event: FormEvent) => {
          event.preventDefault()
          setFilters({ ...filters, search, page: 1 })
        }}
      >
        <input type="search" placeholder="Search username or email" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select value={filters.role ?? ''} onChange={(e) => setFilters({ ...filters, role: e.target.value, page: 1 })} aria-label="Role">
          <option value="">All roles</option>
          {roles.data?.map((r) => (
            <option key={r.id}>{r.name}</option>
          ))}
        </select>
        <select
          value={filters.locked === 'true' ? 'locked' : (filters.is_active ?? '')}
          onChange={(e) => {
            const v = e.target.value
            setFilters({ ...filters, locked: v === 'locked' ? 'true' : undefined, is_active: v === 'locked' ? undefined : v, page: 1 })
          }}
          aria-label="Status"
        >
          <option value="">Any status</option>
          <option value="true">Active</option>
          <option value="false">Disabled</option>
          <option value="locked">Locked</option>
        </select>
        <button className="btn">Search</button>
      </form>

      {users.isPending && <Loading />}
      {users.data && users.data.results.length === 0 && <EmptyState>No users match.</EmptyState>}
      {users.data && users.data.results.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>User</th>
                <th>Roles</th>
                <th>Access groups</th>
                <th>Status</th>
                <th>MFA</th>
                <th>Last sign-in</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {users.data.results.map((user) => (
                <tr key={user.id} className={user.id === editing ? 'selected' : undefined}>
                  <td>
                    <strong>{user.username}</strong>
                    <br />
                    <span className="muted">{user.display_name || user.email}</span>
                  </td>
                  <td>{user.roles.map((r) => r.name).join(', ')}</td>
                  <td>{user.access_groups.map((g) => g.name).join(', ') || '—'}</td>
                  <td>{userStatus(user)}</td>
                  <td>{user.mfa_enabled ? <StatusBadge label="On" tone="ok" /> : <StatusBadge label="Off" />}</td>
                  <td>{formatDateTime(user.last_login)}</td>
                  <td>
                    <button type="button" className="btn btn-small" onClick={() => setEditing(user.id === editing ? null : user.id)}>
                      {user.id === editing ? 'Close' : 'Edit'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {users.data && (users.data.next || users.data.previous) && (
        <div className="pager">
          <button type="button" className="btn btn-small" disabled={!users.data.previous} onClick={() => setFilters({ ...filters, page: page - 1 })}>
            Previous
          </button>
          <span className="muted">Page {page}</span>
          <button type="button" className="btn btn-small" disabled={!users.data.next} onClick={() => setFilters({ ...filters, page: page + 1 })}>
            Next
          </button>
        </div>
      )}

      {selected && roles.data && groups.data && <UserEditor key={selected.id} user={selected} roles={roles.data} groups={groups.data} />}
    </>
  )
}

function NewUserForm({ roles, groups, onDone }: { roles: Role[]; groups: AccessGroup[]; onDone: () => void }) {
  const queryClient = useQueryClient()
  const general = groups.find((g) => g.name === 'general')
  const [form, setForm] = useState<admin.NewUser>({
    username: '',
    email: '',
    display_name: '',
    auth_source: 'LOCAL',
    password: '',
    role_ids: [],
    access_group_ids: general ? [general.id] : [],
  })
  const create = useMutation({
    mutationFn: () => admin.createUser(form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      onDone()
    },
  })
  const error = create.error instanceof ApiError ? create.error : null
  const toggle = (list: string[], id: string) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id])
  const fieldError = (name: string) => error?.fieldErrors(name).map((m) => <span className="field-error" key={m}>{m}</span>)

  return (
    <section className="panel">
      <h2>New user</h2>
      <form
        className="form-grid"
        onSubmit={(event: FormEvent) => {
          event.preventDefault()
          create.mutate()
        }}
      >
        <label>
          Username
          <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required />
          {fieldError('username')}
        </label>
        <label>
          Email
          <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
          {fieldError('email')}
        </label>
        <label>
          Name
          <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
        </label>
        <label>
          Sign-in
          <select value={form.auth_source} onChange={(e) => setForm({ ...form, auth_source: e.target.value as 'LOCAL' | 'LDAP' })}>
            <option value="LOCAL">Local password</option>
            <option value="LDAP">LDAP / Active Directory</option>
          </select>
        </label>
        {form.auth_source === 'LOCAL' && (
          <label>
            First password (at least 12 characters; they can change it)
            <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} autoComplete="new-password" />
            {fieldError('password')}
          </label>
        )}
        <fieldset>
          <legend>Roles (every account is a User)</legend>
          {roles.map((role) => (
            <label key={role.id} className="check">
              <input
                type="checkbox"
                checked={role.name === USER_ROLE || form.role_ids.includes(role.id)}
                disabled={role.name === USER_ROLE}
                onChange={() => setForm({ ...form, role_ids: toggle(form.role_ids, role.id) })}
              />
              {role.name}
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend>Access groups</legend>
          {groups.map((group) => (
            <label key={group.id} className="check">
              <input
                type="checkbox"
                checked={form.access_group_ids?.includes(group.id) ?? false}
                onChange={() => setForm({ ...form, access_group_ids: toggle(form.access_group_ids ?? [], group.id) })}
              />
              {group.name}
            </label>
          ))}
        </fieldset>
        {error && error.code !== 'validation_error' && <p className="alert alert-error">{error.message}</p>}
        <div className="actions">
          <button type="button" className="btn" onClick={onDone}>
            Cancel
          </button>
          <button className="btn btn-primary" disabled={create.isPending}>
            Create user
          </button>
        </div>
      </form>
    </section>
  )
}

function UserEditor({ user, roles, groups }: { user: AdminUser; roles: Role[]; groups: AccessGroup[] }) {
  const queryClient = useQueryClient()
  const [roleIds, setRoleIds] = useState(user.roles.map((r) => r.id))
  const [groupIds, setGroupIds] = useState(user.access_groups.map((g) => g.id))
  const [profile, setProfile] = useState({ display_name: user.display_name, email: user.email })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['admin-users'] })
  const saveProfile = useMutation({ mutationFn: () => admin.updateUser(user.id, profile), onSuccess: refresh })
  const saveRoles = useMutation({ mutationFn: () => admin.setUserRoles(user.id, roleIds), onSuccess: refresh })
  const saveGroups = useMutation({ mutationFn: () => admin.setUserAccessGroups(user.id, groupIds), onSuccess: refresh })
  const setActive = useMutation({ mutationFn: (is_active: boolean) => admin.updateUser(user.id, { is_active }), onSuccess: refresh })
  const unlock = useMutation({ mutationFn: () => admin.unlockUser(user.id), onSuccess: refresh })
  const resetMfa = useMutation({ mutationFn: () => admin.resetUserMfa(user.id), onSuccess: refresh })
  const toggle = (list: string[], id: string) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id])
  const anyError = saveProfile.error ?? saveRoles.error ?? saveGroups.error ?? setActive.error ?? unlock.error ?? resetMfa.error

  return (
    <section className="panel" aria-label={`Edit ${user.username}`}>
      <h2>Edit {user.username}</h2>
      <ErrorMessage error={anyError} />
      <div className="grid-3">
        <div>
          <h3>Profile</h3>
          <label>
            Name
            <input value={profile.display_name} onChange={(e) => setProfile({ ...profile, display_name: e.target.value })} />
          </label>
          <label>
            Email
            <input type="email" value={profile.email} onChange={(e) => setProfile({ ...profile, email: e.target.value })} />
          </label>
          <button type="button" className="btn" onClick={() => saveProfile.mutate()} disabled={saveProfile.isPending}>
            Save profile
          </button>
        </div>
        <div>
          <h3>Roles</h3>
          {roles.map((role) => (
            <label key={role.id} className="check" title={role.description}>
              <input
                type="checkbox"
                checked={role.name === USER_ROLE || roleIds.includes(role.id)}
                disabled={role.name === USER_ROLE}
                onChange={() => setRoleIds(toggle(roleIds, role.id))}
              />
              {role.name}
            </label>
          ))}
          <button type="button" className="btn" onClick={() => saveRoles.mutate()} disabled={saveRoles.isPending}>
            Save roles
          </button>
        </div>
        <div>
          <h3>Access groups</h3>
          {groups.map((group) => (
            <label key={group.id} className="check">
              <input type="checkbox" checked={groupIds.includes(group.id)} onChange={() => setGroupIds(toggle(groupIds, group.id))} />
              {group.name}
            </label>
          ))}
          <button type="button" className="btn" onClick={() => saveGroups.mutate()} disabled={saveGroups.isPending}>
            Save access groups
          </button>
        </div>
      </div>
      <div className="actions">
        {user.is_locked && (
          <button type="button" className="btn" onClick={() => unlock.mutate()}>
            Unlock (locked until {formatDateTime(user.locked_until)})
          </button>
        )}
        {user.mfa_enabled && (
          <ConfirmButton
            label="Reset MFA"
            title={`Reset MFA for ${user.username}?`}
            message="Their authenticator app stops working and all their sessions end. They must set it up again."
            danger
            onConfirm={() => resetMfa.mutate()}
          />
        )}
        {user.is_active ? (
          <ConfirmButton
            label="Disable account"
            title={`Disable ${user.username}?`}
            message="They are signed out everywhere and cannot sign in until the account is enabled again."
            danger
            onConfirm={() => setActive.mutate(false)}
          />
        ) : (
          <button type="button" className="btn" onClick={() => setActive.mutate(true)}>
            Enable account
          </button>
        )}
      </div>
    </section>
  )
}
