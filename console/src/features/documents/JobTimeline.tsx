import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as documents from '../../api/documents'
import type { StepRun } from '../../api/types'
import { useCan } from '../../auth/session'
import { ErrorMessage, Loading } from '../../components/Feedback'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../lib/format'
import { IN_PROGRESS, toneFor } from '../../lib/status'

const STEP_TEXT: Record<string, string> = {
  'read.minio_original': 'Read the original file',
  'parse.docling': 'Parse text, layout and tables',
  'parse.pymupdf': 'Parse PDF text',
  'parse.plain': 'Read plain text',
  'ocr.tesseract': 'OCR scanned pages',
  'ocr.easyocr': 'OCR (EasyOCR)',
  'clean.normalize': 'Clean the text',
  'structure.rebuild': 'Rebuild headings and sections',
  'enrich.none': 'Enrich (off)',
  'chunk.structure_aware': 'Split into chunks',
  'chunk.quality_checks': 'Check chunk quality',
  'chunk.persist': 'Save chunks',
  'embed.sentence_transformers': 'Create embeddings',
}

function summary(step: StepRun): string {
  const out = step.output_summary ?? {}
  if (out.reason) return String(out.reason)
  const parts = Object.entries(out)
    .filter(([, v]) => typeof v === 'number' || typeof v === 'string')
    .slice(0, 4)
    .map(([k, v]) => `${k.replaceAll('_', ' ')}: ${v}`)
  return parts.join(' · ')
}

export function JobTimeline({ jobId }: { jobId: string }) {
  const can = useCan()
  const queryClient = useQueryClient()
  const job = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => documents.getJob(jobId),
    refetchInterval: (query) => (query.state.data && IN_PROGRESS.has(query.state.data.status) ? 2000 : false),
  })
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['job', jobId] })
    queryClient.invalidateQueries({ queryKey: ['document'] })
  }
  const retry = useMutation({ mutationFn: () => documents.retryJob(jobId), onSuccess: refresh })
  const cancel = useMutation({ mutationFn: () => documents.cancelJob(jobId), onSuccess: refresh })
  if (job.isPending) return <Loading />
  if (!job.data) return <ErrorMessage error={job.error} />
  const j = job.data

  return (
    <section className="panel">
      <h2>
        Processing <StatusBadge label={j.status} tone={toneFor(j.status)} />
      </h2>
      <p className="muted">
        {j.job_type === 'REPROCESS' ? 'Reprocessing' : 'Ingest'} with {j.pipeline_version} · attempt {j.attempt_count || 1} · started {formatDateTime(j.started_at)}
        {j.completed_at && ` · finished ${formatDateTime(j.completed_at)}`}
      </p>
      {j.error_message && <p className="alert alert-error">{j.error_message}</p>}
      {j.status === 'QUEUED' && j.steps.length === 0 && <p className="muted">Waiting for the worker…</p>}
      <ol className="timeline">
        {j.steps.map((step) => (
          <li key={step.id} className={`timeline-step timeline-${step.status.toLowerCase()}`}>
            <span className="timeline-dot" aria-hidden />
            <div>
              <strong>{STEP_TEXT[step.step_name] ?? step.step_name}</strong> <StatusBadge label={step.status} tone={toneFor(step.status)} />
              {step.duration_ms !== null && <span className="muted"> {(step.duration_ms / 1000).toFixed(1)} s</span>}
              <div className="muted small">{step.error_message ?? summary(step)}</div>
            </div>
          </li>
        ))}
      </ol>
      {can('jobs.retry') && (
        <div className="actions">
          {j.status === 'FAILED' && (
            <button type="button" className="btn btn-primary" onClick={() => retry.mutate()} disabled={retry.isPending}>
              Retry
            </button>
          )}
          {['QUEUED', 'RUNNING', 'RETRY'].includes(j.status) && (
            <button type="button" className="btn btn-danger" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
              Cancel
            </button>
          )}
          <ErrorMessage error={retry.error ?? cancel.error} />
        </div>
      )}
    </section>
  )
}
