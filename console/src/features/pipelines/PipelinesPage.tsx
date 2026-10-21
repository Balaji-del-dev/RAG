import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { listPipelines } from '../../api/pipelines'
import { EmptyState, ErrorMessage, Loading, PageHeader } from '../../components/Feedback'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../lib/format'
import { VERSION_TONE } from './status'

export default function PipelinesPage() {
  const pipelines = useQuery({ queryKey: ['pipelines'], queryFn: listPipelines })

  return (
    <>
      <PageHeader
        title="Pipelines"
        description="How documents are read, chunked and embedded, and how answers are found. Drafts can be edited; published versions never change."
      />
      <ErrorMessage error={pipelines.error} />
      {pipelines.isPending && <Loading />}
      {pipelines.data?.length === 0 && <EmptyState>No pipelines yet.</EmptyState>}
      {pipelines.data?.map((pipeline) => (
        <section className="panel" key={pipeline.id}>
          <h2>
            {pipeline.name} {pipeline.is_active && <StatusBadge label="Active" tone="ok" />}
          </h2>
          {pipeline.description && <p className="muted">{pipeline.description}</p>}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Version</th>
                  <th>Status</th>
                  <th>Author</th>
                  <th>Published</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {pipeline.versions.map((version) => (
                  <tr key={version.id}>
                    <td>
                      <strong>v{version.version_number}</strong>
                    </td>
                    <td>
                      <StatusBadge label={version.status} tone={VERSION_TONE[version.status]} />
                    </td>
                    <td>{version.created_by ?? 'system'}</td>
                    <td>{formatDateTime(version.published_at)}</td>
                    <td>
                      <Link className="btn btn-small" to={`/pipelines/${pipeline.id}/versions/${version.id}`}>
                        Open
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </>
  )
}
