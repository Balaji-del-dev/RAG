import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import * as indexes from '../../api/indexes'
import { listPipelines } from '../../api/pipelines'
import type { Generation } from '../../api/types'
import { useCan } from '../../auth/session'
import { ConfirmButton } from '../../components/ConfirmButton'
import { EmptyState, ErrorMessage, Loading, PageHeader } from '../../components/Feedback'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../lib/format'
import { toneFor } from '../../lib/status'

const CHECK_TEXT: Record<string, string> = {
  COUNT: 'Same number of chunks in Qdrant, OpenSearch and PostgreSQL',
  MISSING: 'No chunk missing from either engine',
  ORPHAN: 'No leftover records that PostgreSQL does not know',
  DUPLICATE: 'No duplicate memberships',
  SMOKE_DENSE: 'Dense search finds sample chunks',
  SMOKE_LEXICAL: 'BM25 search finds sample chunks',
  SMOKE_HYBRID: 'Both searches find them',
}

export default function IndexesPage() {
  const can = useCan()
  const queryClient = useQueryClient()
  const generations = useQuery({ queryKey: ['generations'], queryFn: indexes.listGenerations, refetchInterval: 5000 })
  const pipelines = useQuery({ queryKey: ['pipelines'], queryFn: listPipelines, enabled: can('indexes.build') })
  const [open, setOpen] = useState<string | null>(null)
  const [versionId, setVersionId] = useState('')
  const build = useMutation({
    mutationFn: () => indexes.buildGeneration(versionId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['generations'] }),
  })
  const versions = pipelines.data?.flatMap((p) => p.versions.map((v) => ({ id: v.id, label: `${p.name} v${v.version_number} (${v.status})` }))) ?? []

  return (
    <>
      <PageHeader
        title="Search indexes"
        description="Each generation is one Qdrant collection plus one OpenSearch index. PostgreSQL decides which one is live; both always switch together."
      />
      {can('indexes.build') && (
        <section className="panel">
          <h2>Build a generation</h2>
          <p className="muted">Fills a generation for a pipeline version from every live document; documents not yet processed with that version are reprocessed first.</p>
          <div className="toolbar">
            <select aria-label="Pipeline version" value={versionId} onChange={(e) => setVersionId(e.target.value)}>
              <option value="">Choose a pipeline version…</option>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.label}
                </option>
              ))}
            </select>
            <button type="button" className="btn btn-primary" disabled={!versionId || build.isPending} onClick={() => build.mutate()}>
              Build
            </button>
          </div>
          <ErrorMessage error={build.error} />
        </section>
      )}
      <ErrorMessage error={generations.error} />
      {generations.isPending && <Loading />}
      {generations.data?.length === 0 && <EmptyState>No index generations yet. The first one is created when the first document is processed.</EmptyState>}
      {generations.data?.map((g) => (
        <GenerationPanel key={g.id} generation={g} expanded={open === g.id} onToggle={() => setOpen(open === g.id ? null : g.id)} />
      ))}
    </>
  )
}

function GenerationPanel({ generation: g, expanded, onToggle }: { generation: Generation; expanded: boolean; onToggle: () => void }) {
  const can = useCan()
  const queryClient = useQueryClient()
  const detail = useQuery({ queryKey: ['generation', g.id], queryFn: () => indexes.getGeneration(g.id), enabled: expanded, refetchInterval: expanded ? 4000 : false })
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['generations'] })
    queryClient.invalidateQueries({ queryKey: ['generation', g.id] })
  }
  const validate = useMutation({ mutationFn: () => indexes.validateGeneration(g.id), onSuccess: refresh })
  const publish = useMutation({ mutationFn: () => indexes.publishGeneration(g.id), onSuccess: refresh })
  const rollback = useMutation({ mutationFn: () => indexes.rollbackGeneration(g.id), onSuccess: refresh })

  return (
    <section className={g.status === 'PUBLISHED' ? 'panel panel-live' : 'panel'}>
      <div className="page-header">
        <div>
          <h2>
            Generation {g.generation_number} <StatusBadge label={g.status} tone={toneFor(g.status)} />
            {g.status === 'PUBLISHED' && <StatusBadge label="LIVE" tone="ok" />}
          </h2>
          <p className="muted">
            {g.pipeline_version_label} · {g.counts.documents} documents · {g.counts.chunks} chunks · Qdrant <code>{g.qdrant_collection}</code> · OpenSearch{' '}
            <code>{g.opensearch_index}</code>
            {g.published_at && ` · live since ${formatDateTime(g.published_at)}`}
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-small" onClick={onToggle}>
            {expanded ? 'Hide checks' : 'Show checks'}
          </button>
          {can('indexes.build') && g.status !== 'RETIRED' && (
            <button type="button" className="btn btn-small" onClick={() => validate.mutate()} disabled={validate.isPending}>
              Validate
            </button>
          )}
          {can('releases.approve') && g.status !== 'PUBLISHED' && g.status !== 'RETIRED' && (
            <ConfirmButton
              label="Publish"
              title={`Make generation ${g.generation_number} live?`}
              message="Questions are answered from it at once. The first generation can be published here; later ones go through evaluation and approval."
              disabled={!g.validated}
              onConfirm={() => publish.mutate()}
            />
          )}
          {can('releases.approve') && g.status === 'RETIRED' && (
            <ConfirmButton
              label="Roll back to this"
              title={`Make generation ${g.generation_number} live again?`}
              message="The current live generation is retired, and this one answers questions again."
              danger
              onConfirm={() => rollback.mutate()}
            />
          )}
        </div>
      </div>
      {validate.isSuccess && <p className="muted">Validation is running… results appear below in a few seconds.</p>}
      {!g.validated && g.status !== 'PUBLISHED' && g.status !== 'RETIRED' && <p className="muted small">Publish needs every check to pass — press Validate.</p>}
      <ErrorMessage error={validate.error ?? publish.error ?? rollback.error} />
      {expanded && detail.data && (
        <ul className="checks">
          {detail.data.validations.length === 0 && <li className="muted">Not validated yet.</li>}
          {detail.data.validations.map((v) => (
            <li key={v.id}>
              <StatusBadge label={v.status} tone={toneFor(v.status)} /> {CHECK_TEXT[v.validation_type] ?? v.validation_type}
              {v.expected_count !== null && (
                <span className="muted">
                  {' '}
                  (expected {v.expected_count}, got {v.actual_count})
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
