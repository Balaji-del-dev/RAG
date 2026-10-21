import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import * as retrieval from '../../api/retrieval'
import type { FailureCase } from '../../api/types'
import { EmptyState, ErrorMessage, Loading, PageHeader } from '../../components/Feedback'
import { StatusBadge, type Tone } from '../../components/StatusBadge'
import { formatDateTime } from '../../lib/format'

const REVIEW_TONE: Record<FailureCase['review_status'], Tone> = { OPEN: 'warn', IN_REVIEW: 'info', RESOLVED: 'ok', WONT_FIX: 'neutral' }
const TYPES = ['NO_RETRIEVAL', 'WRONG_RETRIEVAL', 'NOT_GROUNDED', 'WRONG_CITATION', 'INCOMPLETE', 'FORMAT', 'SAFETY', 'LATENCY']

export default function FailuresPage() {
  const [status, setStatus] = useState('OPEN')
  const [page, setPage] = useState(1)
  const cases = useQuery({ queryKey: ['failure-cases', status, page], queryFn: () => retrieval.listFailureCases(status, page), placeholderData: keepPreviousData })
  return (
    <>
      <PageHeader
        title="Failure cases"
        description="Answers people rated 1–2 stars. Find the root cause, fix it in a new pipeline version, and add resolved cases to an evaluation dataset."
      />
      <div className="toolbar">
        <select aria-label="Review status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }}>
          <option value="">All</option>
          <option value="OPEN">Open</option>
          <option value="IN_REVIEW">In review</option>
          <option value="RESOLVED">Resolved</option>
          <option value="WONT_FIX">Won't fix</option>
        </select>
      </div>
      <ErrorMessage error={cases.error} />
      {cases.isPending && <Loading />}
      {cases.data?.results.length === 0 && <EmptyState>No failure cases here.</EmptyState>}
      {cases.data?.results.map((c) => (
        <FailureRow key={c.id} item={c} />
      ))}
      {cases.data && (cases.data.next || cases.data.previous) && (
        <div className="pager">
          <button type="button" className="btn btn-small" disabled={!cases.data.previous} onClick={() => setPage(page - 1)}>
            Previous
          </button>
          <span className="muted">Page {page}</span>
          <button type="button" className="btn btn-small" disabled={!cases.data.next} onClick={() => setPage(page + 1)}>
            Next
          </button>
        </div>
      )}
    </>
  )
}

function FailureRow({ item }: { item: FailureCase }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    failure_type: item.failure_type,
    root_cause: item.root_cause ?? '',
    resolution_notes: item.resolution_notes ?? '',
    review_status: item.review_status,
  })
  const save = useMutation({
    mutationFn: () => retrieval.updateFailureCase(item.id, form),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['failure-cases'] }),
  })
  return (
    <section className="panel">
      <p className="question">{item.question}</p>
      <p className="muted small">
        asked by {item.asked_by} · {formatDateTime(item.asked_at)} · outcome {item.run_status} <StatusBadge label={item.review_status} tone={REVIEW_TONE[item.review_status]} />
      </p>
      <div className="form-grid">
        <label>
          What went wrong
          <select value={form.failure_type} onChange={(e) => setForm({ ...form, failure_type: e.target.value })}>
            {TYPES.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label>
          Review status
          <select value={form.review_status} onChange={(e) => setForm({ ...form, review_status: e.target.value as FailureCase['review_status'] })}>
            <option value="OPEN">Open</option>
            <option value="IN_REVIEW">In review</option>
            <option value="RESOLVED">Resolved</option>
            <option value="WONT_FIX">Won't fix</option>
          </select>
        </label>
        <label>
          Root cause
          <input value={form.root_cause} onChange={(e) => setForm({ ...form, root_cause: e.target.value })} />
        </label>
        <label>
          Resolution notes
          <input value={form.resolution_notes} onChange={(e) => setForm({ ...form, resolution_notes: e.target.value })} />
        </label>
        <div className="actions">
          <button type="button" className="btn btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>
            Save review
          </button>
          {save.isSuccess && <span className="muted">Saved.</span>}
        </div>
      </div>
      <ErrorMessage error={save.error} />
    </section>
  )
}
