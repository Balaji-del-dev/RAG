import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { listAuditEvents, type AuditFilters } from '../../api/evaluation'
import { EmptyState, ErrorMessage, Loading, PageHeader } from '../../components/Feedback'
import { formatDateTime } from '../../lib/format'

export default function AuditLogPage() {
  const [draft, setDraft] = useState<AuditFilters>({})
  const [filters, setFilters] = useState<AuditFilters>({ page: 1 })
  const events = useQuery({ queryKey: ['audit', filters], queryFn: () => listAuditEvents(filters), placeholderData: keepPreviousData })
  const page = filters.page ?? 1
  return (
    <>
      <PageHeader title="Audit log" description="Every sign-in, upload, access change, release and admin action — who, what, when and from where. It can't be edited." />
      <form
        className="toolbar"
        onSubmit={(e: FormEvent) => {
          e.preventDefault()
          setFilters({ ...draft, page: 1 })
        }}
      >
        <input placeholder="Who (username)" value={draft.actor ?? ''} onChange={(e) => setDraft({ ...draft, actor: e.target.value })} aria-label="Actor" />
        <input placeholder="What, e.g. auth. or document." value={draft.event_type ?? ''} onChange={(e) => setDraft({ ...draft, event_type: e.target.value })} aria-label="Event type" />
        <input type="date" value={draft.since ?? ''} onChange={(e) => setDraft({ ...draft, since: e.target.value })} aria-label="From" />
        <input type="date" value={draft.until ?? ''} onChange={(e) => setDraft({ ...draft, until: e.target.value })} aria-label="Until" />
        <button className="btn">Filter</button>
      </form>
      <ErrorMessage error={events.error} />
      {events.isPending && <Loading />}
      {events.data?.results.length === 0 && <EmptyState>No events match.</EmptyState>}
      {events.data && events.data.results.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>What</th>
                <th>Where</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {events.data.results.map((e) => (
                <tr key={e.id}>
                  <td>{formatDateTime(e.created_at)}</td>
                  <td>{e.actor}</td>
                  <td>
                    <code>{e.event_type}</code>
                    <br />
                    <span className="muted small">{e.entity_type}</span>
                  </td>
                  <td>{e.ip_address ?? '—'}</td>
                  <td className="small">
                    {Object.entries(e.details_json)
                      .slice(0, 4)
                      .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
                      .join(' · ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {events.data && (events.data.next || events.data.previous) && (
        <div className="pager">
          <button type="button" className="btn btn-small" disabled={!events.data.previous} onClick={() => setFilters({ ...filters, page: page - 1 })}>
            Previous
          </button>
          <span className="muted">Page {page}</span>
          <button type="button" className="btn btn-small" disabled={!events.data.next} onClick={() => setFilters({ ...filters, page: page + 1 })}>
            Next
          </button>
        </div>
      )}
    </>
  )
}
