import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import * as admin from '../../api/admin'
import { ApiError } from '../../api/client'
import type { AccessGroup } from '../../api/types'
import { ConfirmButton } from '../../components/ConfirmButton'
import { ErrorMessage, Loading, PageHeader } from '../../components/Feedback'
import { formatDateTime } from '../../lib/format'

const KEY = ['admin-access-groups']

export default function AccessGroupsPage() {
  const groups = useQuery({ queryKey: KEY, queryFn: admin.listAccessGroups })
  return (
    <>
      <PageHeader
        title="Access groups"
        description="Documents are shared with groups. People see a document only if they are in one of its groups — in search results too."
      />
      <NewGroupForm />
      <ErrorMessage error={groups.error} />
      {groups.isPending && <Loading />}
      {groups.data && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Description</th>
                <th>Members</th>
                <th>Created</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {groups.data.map((group) => (
                <GroupRow key={group.id} group={group} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

function NewGroupForm() {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const create = useMutation({
    mutationFn: () => admin.createAccessGroup({ name: name.trim(), description }),
    onSuccess: () => {
      setName('')
      setDescription('')
      queryClient.invalidateQueries({ queryKey: KEY })
    },
  })
  const error = create.error instanceof ApiError ? create.error : null
  return (
    <form
      className="toolbar"
      onSubmit={(event: FormEvent) => {
        event.preventDefault()
        create.mutate()
      }}
    >
      <input placeholder="New group name, e.g. finance" value={name} onChange={(e) => setName(e.target.value)} aria-label="Group name" />
      <input placeholder="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} aria-label="Description" />
      <button className="btn btn-primary" disabled={!name.trim() || create.isPending}>
        Add group
      </button>
      {error && <span className="field-error">{error.fieldErrors('name')[0] ?? error.message}</span>}
    </form>
  )
}

function GroupRow({ group }: { group: AccessGroup }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [description, setDescription] = useState(group.description)
  const refresh = () => queryClient.invalidateQueries({ queryKey: KEY })
  const save = useMutation({ mutationFn: () => admin.updateAccessGroup(group.id, { description }), onSuccess: () => { setEditing(false); refresh() } })
  const remove = useMutation({ mutationFn: () => admin.deleteAccessGroup(group.id), onSuccess: refresh })

  return (
    <tr>
      <td>
        <strong>{group.name}</strong>
      </td>
      <td>
        {editing ? (
          <input value={description} onChange={(e) => setDescription(e.target.value)} aria-label={`Description of ${group.name}`} />
        ) : (
          group.description || <span className="muted">—</span>
        )}
        <ErrorMessage error={save.error ?? remove.error} />
      </td>
      <td>{group.member_count ?? 0}</td>
      <td>{formatDateTime(group.created_at)}</td>
      <td className="row-actions">
        {editing ? (
          <button type="button" className="btn btn-small btn-primary" onClick={() => save.mutate()}>
            Save
          </button>
        ) : (
          <button type="button" className="btn btn-small" onClick={() => setEditing(true)}>
            Edit
          </button>
        )}
        {group.name !== 'general' && (
          <ConfirmButton
            label="Delete"
            title={`Delete the group "${group.name}"?`}
            message="Members lose access to documents shared only with this group. A group that still has documents cannot be deleted."
            danger
            onConfirm={() => remove.mutate()}
          />
        )}
      </td>
    </tr>
  )
}
