import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import * as admin from '../../api/admin'
import { ConfirmButton } from '../../components/ConfirmButton'
import { EmptyState, ErrorMessage, Loading, PageHeader } from '../../components/Feedback'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime, shortUserAgent } from '../../lib/format'

export default function SessionsPage() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const sessions = useQuery({ queryKey: ['admin-sessions', page], queryFn: () => admin.listSessions(page), placeholderData: keepPreviousData })
  const revoke = useMutation({
    mutationFn: admin.revokeSession,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-sessions'] }),
  })

  return (
    <>
      <PageHeader title="Active sessions" description="Everyone signed in right now. Revoking a session signs that browser out on its next request." />
      <ErrorMessage error={sessions.error ?? revoke.error} />
      {sessions.isPending && <Loading />}
      {sessions.data && sessions.data.results.length === 0 && <EmptyState>Nobody is signed in.</EmptyState>}
      {sessions.data && sessions.data.results.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>User</th>
                <th>Device</th>
                <th>IP address</th>
                <th>Signed in</th>
                <th>Last active</th>
                <th>Ends</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {sessions.data.results.map((row) => (
                <tr key={row.id}>
                  <td>
                    <strong>{row.username}</strong> {row.is_current && <StatusBadge label="You, here" tone="info" />}
                  </td>
                  <td>{shortUserAgent(row.user_agent)}</td>
                  <td>{row.ip_address ?? '—'}</td>
                  <td>{formatDateTime(row.created_at)}</td>
                  <td>{formatDateTime(row.last_seen_at)}</td>
                  <td>{formatDateTime(row.expires_at)}</td>
                  <td>
                    <ConfirmButton
                      label="Revoke"
                      title={`Revoke this session of ${row.username}?`}
                      message={row.is_current ? 'This is your own session: you will be signed out.' : 'That browser is signed out on its next request.'}
                      danger
                      onConfirm={() => revoke.mutate(row.id)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {sessions.data && (sessions.data.next || sessions.data.previous) && (
        <div className="pager">
          <button type="button" className="btn btn-small" disabled={!sessions.data.previous} onClick={() => setPage(page - 1)}>
            Previous
          </button>
          <span className="muted">Page {page}</span>
          <button type="button" className="btn btn-small" disabled={!sessions.data.next} onClick={() => setPage(page + 1)}>
            Next
          </button>
        </div>
      )}
    </>
  )
}
