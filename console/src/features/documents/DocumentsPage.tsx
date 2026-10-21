import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { listDocuments, type DocumentFilters } from '../../api/documents'
import { useCan } from '../../auth/session'
import { EmptyState, ErrorMessage, Loading, PageHeader } from '../../components/Feedback'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../lib/format'
import { formatBytes, IN_PROGRESS, toneFor } from '../../lib/status'

const TYPES = ['pdf', 'docx', 'xlsx', 'pptx', 'txt', 'md', 'csv', 'json', 'xml', 'html']

export default function DocumentsPage() {
  const can = useCan()
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState<DocumentFilters>({ page: 1 })
  const documents = useQuery({
    queryKey: ['documents', filters],
    queryFn: () => listDocuments(filters),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => (query.state.data?.results.some((d) => d.current_version && IN_PROGRESS.has(d.current_version.status)) ? 3000 : false),
  })
  const page = filters.page ?? 1

  return (
    <>
      <PageHeader
        title="Documents"
        description="Documents shared with your access groups. Only these can appear in your answers."
        actions={
          can('documents.upload') && (
            <Link className="btn btn-primary" to="/documents/upload">
              Upload
            </Link>
          )
        }
      />
      <form
        className="toolbar"
        onSubmit={(event: FormEvent) => {
          event.preventDefault()
          setFilters({ ...filters, search, page: 1 })
        }}
      >
        <input type="search" placeholder="Search by file name" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select aria-label="Status" value={filters.status ?? ''} onChange={(e) => setFilters({ ...filters, status: e.target.value, page: 1 })}>
          <option value="">Any status</option>
          <option value="ACTIVE">Searchable</option>
          <option value="PENDING">Being processed</option>
          <option value="FAILED">Failed</option>
        </select>
        <select aria-label="Type" value={filters.type ?? ''} onChange={(e) => setFilters({ ...filters, type: e.target.value, page: 1 })}>
          <option value="">Any type</option>
          {TYPES.map((t) => (
            <option key={t} value={t}>
              .{t}
            </option>
          ))}
        </select>
        <button className="btn">Search</button>
      </form>
      <ErrorMessage error={documents.error} />
      {documents.isPending && <Loading />}
      {documents.data?.results.length === 0 && (
        <EmptyState>{can('documents.upload') ? 'No documents yet. Upload the first one.' : 'No documents are shared with your groups yet.'}</EmptyState>
      )}
      {documents.data && documents.data.results.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Document</th>
                <th>Status</th>
                <th>Version</th>
                <th>Access groups</th>
                <th>Uploaded</th>
              </tr>
            </thead>
            <tbody>
              {documents.data.results.map((doc) => (
                <tr key={doc.id}>
                  <td>
                    <Link to={`/documents/${doc.id}`}>
                      <strong>{doc.filename}</strong>
                    </Link>
                    <br />
                    <span className="muted">
                      .{doc.file_extension} · {doc.current_version ? formatBytes(doc.current_version.file_size) : '—'}
                    </span>
                  </td>
                  <td>
                    <StatusBadge label={doc.lifecycle_status} tone={toneFor(doc.lifecycle_status)} />
                    {doc.current_version && doc.current_version.status !== 'PUBLISHED' && (
                      <StatusBadge label={doc.current_version.status} tone={toneFor(doc.current_version.status)} />
                    )}
                  </td>
                  <td>v{doc.current_version?.version_number ?? '—'}</td>
                  <td>{doc.access_groups.map((g) => g.name).join(', ')}</td>
                  <td>
                    {formatDateTime(doc.created_at)}
                    <br />
                    <span className="muted">by {doc.created_by}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {documents.data && (documents.data.next || documents.data.previous) && (
        <div className="pager">
          <button type="button" className="btn btn-small" disabled={!documents.data.previous} onClick={() => setFilters({ ...filters, page: page - 1 })}>
            Previous
          </button>
          <span className="muted">Page {page}</span>
          <button type="button" className="btn btn-small" disabled={!documents.data.next} onClick={() => setFilters({ ...filters, page: page + 1 })}>
            Next
          </button>
        </div>
      )}
    </>
  )
}
