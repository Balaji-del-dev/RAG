import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import * as evaluation from '../../api/evaluation'
import { useCan } from '../../auth/session'
import { EmptyState, ErrorMessage, Loading, PageHeader } from '../../components/Feedback'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../lib/format'
import { toneFor } from '../../lib/status'

export default function EvaluationPage() {
  const can = useCan()
  const runs = useQuery({
    queryKey: ['eval-runs'],
    queryFn: evaluation.listRuns,
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === 'QUEUED' || r.status === 'RUNNING') ? 4000 : false),
  })
  return (
    <>
      <PageHeader
        title="Evaluation"
        description="Measure a pipeline version against a golden dataset and compare it with the live baseline before it is released."
        actions={
          can('evaluation.manage_datasets') && (
            <Link className="btn" to="/evaluation/datasets">
              Datasets
            </Link>
          )
        }
      />
      {can('evaluation.run') && <StartRun />}
      <ErrorMessage error={runs.error} />
      {runs.isPending && <Loading />}
      {runs.data?.length === 0 && <EmptyState>No evaluation runs yet.</EmptyState>}
      {runs.data && runs.data.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>Status</th>
                <th>Pipeline</th>
                <th>Dataset</th>
                <th>Gates</th>
                <th>Approved</th>
              </tr>
            </thead>
            <tbody>
              {runs.data.map((run) => {
                const gates = run.summary_json.gates ?? []
                return (
                  <tr key={run.id}>
                    <td>
                      <Link to={`/evaluation/runs/${run.id}`}>{formatDateTime(run.started_at)}</Link>
                      <br />
                      <span className="muted small">by {run.summary_json.started_by ?? '—'}</span>
                    </td>
                    <td>
                      <StatusBadge label={run.status} tone={toneFor(run.status === 'PASSED' ? 'PASSED' : run.status === 'ERROR' ? 'FAILED' : run.status)} />
                    </td>
                    <td>
                      {run.pipeline_version_label} · gen {run.generation_number}
                    </td>
                    <td>{run.dataset_label}</td>
                    <td>{gates.length ? `${gates.filter((g) => g.passed).length}/${gates.length} passed` : '—'}</td>
                    <td>{run.approved_by ?? '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

function StartRun() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const datasets = useQuery({ queryKey: ['eval-datasets'], queryFn: evaluation.listDatasets })
  const candidates = useQuery({ queryKey: ['eval-candidates'], queryFn: evaluation.listCandidates })
  const [datasetId, setDatasetId] = useState('')
  const [generationId, setGenerationId] = useState('')
  const [judge, setJudge] = useState(false)
  const candidate = candidates.data?.find((c) => c.index_generation_id === generationId)
  const start = useMutation({
    mutationFn: () =>
      evaluation.startRun({ dataset_id: datasetId, pipeline_version_id: candidate!.pipeline_version_id, index_generation_id: generationId, use_llm_judge: judge }),
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ['eval-runs'] })
      navigate(`/evaluation/runs/${run.id}`)
    },
  })

  return (
    <section className="panel">
      <h2>Start a run</h2>
      <div className="toolbar">
        <select aria-label="Dataset" value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
          <option value="">Dataset…</option>
          {datasets.data?.map((d) => (
            <option key={d.id} value={d.id} disabled={d.case_count === 0}>
              {d.name} v{d.version} ({d.case_count} cases)
            </option>
          ))}
        </select>
        <select aria-label="Candidate" value={generationId} onChange={(e) => setGenerationId(e.target.value)}>
          <option value="">Candidate (pipeline version + index)…</option>
          {candidates.data?.map((c) => (
            <option key={c.index_generation_id} value={c.index_generation_id}>
              {c.label}
            </option>
          ))}
        </select>
        <label className="check">
          <input type="checkbox" checked={judge} onChange={(e) => setJudge(e.target.checked)} />
          LLM judge (faithfulness, relevancy — slow)
        </label>
        <button type="button" className="btn btn-primary" disabled={!datasetId || !generationId || start.isPending} onClick={() => start.mutate()}>
          Start
        </button>
      </div>
      <p className="muted small">Each case runs the full question pipeline on this CPU. Without the judge, a case takes about 20–40 s; with it, several minutes.</p>
      <ErrorMessage error={start.error} />
    </section>
  )
}
