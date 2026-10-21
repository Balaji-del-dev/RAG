import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { ApiError, errorMessage } from '../../api/client'
import * as documents from '../../api/documents'
import type { DocumentDetail } from '../../api/types'
import { useCan } from '../../auth/session'
import { ConfirmButton } from '../../components/ConfirmButton'
import { ErrorMessage, Loading, PageHeader } from '../../components/Feedback'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../lib/format'
import { formatBytes, IN_PROGRESS, toneFor } from '../../lib/status'
import { AccessGroupPicker } from './AccessGroupPicker'
import { JobTimeline } from './JobTimeline'

export default function DocumentDetailPage() {
  const { documentId = '' } = useParams()
  const can = useCan()
  const doc = useQuery({
    queryKey: ['document', documentId],
    queryFn: () => documents.getDocument(documentId),
    refetchInterval: (query) => {
      const d = query.state.data
      const busy = d?.versions.some((v) => IN_PROGRESS.has(v.status)) || (d?.latest_job && IN_PROGRESS.has(d.latest_job.status))
      return busy ? 3000 : false
    },
  })
  if (doc.isPending) return <Loading />
  if (!doc.data) return <ErrorMessage error={doc.error} />
  const d = doc.data

  return (
    <>
      <p className="muted">
        <Link to="/documents">Documents</Link> / {d.filename}
      </p>
      <PageHeader
        title={d.filename}
        description={`.${d.file_extension} · uploaded ${formatDateTime(d.created_at)} by ${d.created_by}`}
        actions={<DocumentActions doc={d} />}
      />
      <p>
        <StatusBadge label={d.lifecycle_status} tone={toneFor(d.lifecycle_status)} />
        <span className="muted">
          {d.lifecycle_status === 'ACTIVE' && ' Searchable: it can appear in answers for its access groups.'}
          {d.lifecycle_status === 'PENDING' &&
            (d.current_version?.status === 'VALIDATING_INDEX'
              ? ' Processed and indexed — it becomes searchable when a Release approver publishes the index.'
              : ' Being processed. This page updates by itself.')}
          {d.lifecycle_status === 'FAILED' && ' Processing failed — see the steps below.'}
        </span>
      </p>
      <div className="grid-2">
        <section className="panel">
          <h2>Versions</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Version</th>
                  <th>Status</th>
                  <th>Size</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {d.versions.map((v) => (
                  <tr key={v.id}>
                    <td>
                      v{v.version_number} {d.current_version?.id === v.id && <StatusBadge label="current" tone="info" />}
                    </td>
                    <td>
                      <StatusBadge label={v.status} tone={toneFor(v.status)} />
                    </td>
                    <td>{formatBytes(v.file_size)}</td>
                    <td>
                      <a className="btn btn-small" href={documents.downloadUrl(d.id, v.version_number)}>
                        Download
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <AccessPanel doc={d} editable={can('documents.manage_access')} />
      </div>
      {can('jobs.view') && d.latest_job && <JobTimeline jobId={d.latest_job.id} />}
    </>
  )
}

function DocumentActions({ doc }: { doc: DocumentDetail }) {
  const can = useCan()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [progress, setProgress] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const remove = useMutation({
    mutationFn: () => documents.deleteDocument(doc.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      navigate('/documents', { replace: true })
    },
  })

  async function newVersion(file: File | undefined) {
    if (!file) return
    setError(null)
    setProgress(0)
    try {
      const updated = await documents.uploadNewVersion(doc.id, file, setProgress)
      queryClient.setQueryData(['document', doc.id], updated)
    } catch (err) {
      setError(err instanceof ApiError ? (err.fieldErrors('file')[0] ?? err.message) : errorMessage(err))
    } finally {
      setProgress(null)
      if (input.current) input.current.value = ''
    }
  }

  if (!can('documents.manage')) return null
  return (
    <div className="actions">
      <button type="button" className="btn" disabled={progress !== null} onClick={() => input.current?.click()}>
        {progress !== null ? `Uploading… ${Math.round(progress * 100)}%` : 'Upload new version'}
      </button>
      <input ref={input} type="file" accept={`.${doc.file_extension}`} hidden aria-label="New version file" onChange={(e) => newVersion(e.target.files?.[0])} />
      <ConfirmButton
        label="Delete"
        title={`Delete ${doc.filename}?`}
        message="It disappears from the document list and from every answer at once. Its files are removed from storage."
        danger
        onConfirm={() => remove.mutate()}
      />
      {error && <span className="field-error">{error}</span>}
      <ErrorMessage error={remove.error} />
    </div>
  )
}

function AccessPanel({ doc, editable }: { doc: DocumentDetail; editable: boolean }) {
  const queryClient = useQueryClient()
  const [ids, setIds] = useState(doc.access_groups.map((g) => g.id))
  const save = useMutation({
    mutationFn: () => documents.setDocumentAccess(doc.id, ids),
    onSuccess: (updated) => queryClient.setQueryData(['document', doc.id], updated),
  })
  return (
    <section className="panel">
      <h2>Who can read it</h2>
      {!editable && <p>{doc.access_groups.map((g) => g.name).join(', ')}</p>}
      {editable && (
        <>
          <AccessGroupPicker value={ids} onChange={setIds} legend="Access groups" />
          <div className="actions">
            <button type="button" className="btn btn-primary" disabled={ids.length === 0 || save.isPending} onClick={() => save.mutate()}>
              Save access
            </button>
            {save.isSuccess && <span className="muted">Saved — both search indexes are being updated.</span>}
          </div>
          <ErrorMessage error={save.error} />
        </>
      )}
    </section>
  )
}
