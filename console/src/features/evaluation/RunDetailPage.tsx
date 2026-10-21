import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import * as evaluation from '../../api/evaluation'
import type { EvalRunDetail } from '../../api/types'
import { useCan, useSession } from '../../auth/session'
import { ConfirmButton } from '../../components/ConfirmButton'
import { ErrorMessage, Loading, PageHeader } from '../../components/Feedback'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../lib/format'
import { toneFor } from '../../lib/status'

const METRIC_TEXT: Record<string, string> = {
  'hit@5': 'An expected document is in the top 5',
  'recall@5': 'Share of expected documents in the top 5',
  mrr: 'How high the first right document ranks (MRR)',
  answer_keyword_recall: "The answer contains the expected answer's key words",
  abstention_correct: 'Says "not found" when the documents have no answer',
  access_safe: 'Never shows documents outside the asker’s groups',
  faithfulness: 'Answer supported by its sources (LLM judge)',
  answer_relevancy: 'Answer addresses the question (LLM judge)',
}

const pct = (value: number | null | undefined) => (value === null || value === undefined ? '—' : `${Math.round(value * 100)}%`)

export default function RunDetailPage() {
  const { runId = '' } = useParams()
  const run = useQuery({
    queryKey: ['eval-run', runId],
    queryFn: () => evaluation.getRun(runId),
    refetchInterval: (q) => (q.state.data && ['QUEUED', 'RUNNING'].includes(q.state.data.status) ? 4000 : false),
  })
  if (run.isPending) return <Loading />
  if (!run.data) return <ErrorMessage error={run.error} />
  const r = run.data
  const s = r.summary_json

  return (
    <>
      <p className="muted">
        <Link to="/evaluation">Evaluation</Link> / run {formatDateTime(r.started_at)}
      </p>
      <PageHeader
        title={`${r.pipeline_version_label} · generation ${r.generation_number}`}
        description={`${r.dataset_label} · started by ${s.started_by ?? '—'}${s.use_llm_judge ? ' · with LLM judge' : ''}${r.completed_at ? ` · finished ${formatDateTime(r.completed_at)}` : ''}`}
        actions={<Approve run={r} />}
      />
      <p>
        <StatusBadge label={r.status} tone={toneFor(r.status === 'ERROR' ? 'FAILED' : r.status)} />
        {r.status === 'RUNNING' && <span className="muted"> Running {s.cases ?? ''} cases… this page updates by itself.</span>}
        {r.status === 'QUEUED' && <span className="muted"> Waiting for the worker…</span>}
        {r.approved_by && <span className="muted"> Approved by {r.approved_by}.</span>}
      </p>
      {s.error && <p className="alert alert-error">{s.error}</p>}
      {s.gates && s.gates.length > 0 && (
        <section className="panel">
          <h2>Metrics against the baseline</h2>
          <p className="muted small">{s.baseline_run_id ? 'Baseline: the latest run of this dataset on the live pipeline.' : 'No baseline yet — this run can become one.'}</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>This run</th>
                  <th>Baseline</th>
                  <th>Gate</th>
                </tr>
              </thead>
              <tbody>
                {s.gates.map((g) => (
                  <tr key={g.metric}>
                    <td>
                      <strong>{g.metric}</strong>
                      <br />
                      <span className="muted small">{METRIC_TEXT[g.metric] ?? ''}</span>
                    </td>
                    <td>
                      <div className="bar" aria-label={`${g.metric} ${pct(g.value)}`}>
                        <div style={{ width: `${Math.round(g.value * 100)}%` }} />
                        <span>{pct(g.value)}</span>
                      </div>
                    </td>
                    <td>{pct(g.baseline)}</td>
                    <td>
                      <StatusBadge label={g.passed ? 'PASSED' : 'FAILED'} tone={g.passed ? 'ok' : 'bad'} />
                      <span className="muted small">
                        {' '}
                        {g.min !== null && `≥ ${pct(g.min)}`}
                        {g.max_drop !== null && ` · drop ≤ ${pct(g.max_drop)}`}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {r.results.length > 0 && <CaseResults run={r} />}
    </>
  )
}

function CaseResults({ run }: { run: EvalRunDetail }) {
  const byCase = new Map<string, EvalRunDetail['results']>()
  for (const row of run.results) byCase.set(row.evaluation_case, [...(byCase.get(row.evaluation_case) ?? []), row])
  return (
    <section className="panel">
      <h2>Cases</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Question</th>
              <th>Type</th>
              <th>Results</th>
            </tr>
          </thead>
          <tbody>
            {[...byCase.values()].map((rows) => (
              <tr key={rows[0].evaluation_case}>
                <td>{rows[0].question}</td>
                <td>{rows[0].case_type}</td>
                <td>
                  {rows.map((row) => (
                    <div key={row.id}>
                      <StatusBadge label={`${row.metric_name} ${pct(row.score)}`} tone={row.passed ? 'ok' : 'bad'} />
                      {typeof row.details_json.reason === 'string' && <span className="muted small"> {row.details_json.reason}</span>}
                      {Array.isArray(row.details_json.leaked) && row.details_json.leaked.length > 0 && (
                        <span className="field-error"> leaked: {(row.details_json.leaked as string[]).join(', ')}</span>
                      )}
                    </div>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function Approve({ run }: { run: EvalRunDetail }) {
  const can = useCan()
  const { me } = useSession()
  const queryClient = useQueryClient()
  const approve = useMutation({
    mutationFn: () => evaluation.approveRun(run.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['eval-run', run.id] })
      queryClient.invalidateQueries({ queryKey: ['eval-runs'] })
    },
  })
  if (!can('releases.approve')) return null
  const reason =
    run.approved_by
      ? `Approved by ${run.approved_by}.`
      : run.is_live
        ? 'This is the live version — this run is its baseline, nothing to release.'
        : run.status !== 'PASSED'
        ? 'Only a run that passed every gate can be approved.'
        : run.pipeline_version_author && run.pipeline_version_author === me?.username
          ? 'You made this pipeline version. Another Release approver must approve it (four-eyes rule).'
          : null
  return (
    <div className="actions">
      <ConfirmButton
        label="Approve and publish"
        title="Approve this release?"
        message={`${run.pipeline_version_label} and index generation ${run.generation_number} become live together. The current live version is retired and kept for rollback.`}
        disabled={reason !== null || approve.isPending}
        onConfirm={() => approve.mutate()}
      />
      {reason && <span className="muted small">{reason}</span>}
      <ErrorMessage error={approve.error} />
    </div>
  )
}
