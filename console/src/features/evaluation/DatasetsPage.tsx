import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { ApiError, errorMessage } from '../../api/client'
import * as evaluation from '../../api/evaluation'
import type { CaseType, Dataset } from '../../api/types'
import { ConfirmButton } from '../../components/ConfirmButton'
import { EmptyState, ErrorMessage, Loading, PageHeader } from '../../components/Feedback'
import { StatusBadge } from '../../components/StatusBadge'

const CASE_TYPES: [CaseType, string][] = [
  ['FACTUAL', 'Factual — has an answer in the documents'],
  ['MULTI_HOP', 'Multi-step — needs several passages'],
  ['TABLE', 'Table — answer is in a table'],
  ['NO_ANSWER', 'No answer — the system must say "not found"'],
  ['ACCESS', 'Access — must NOT see the listed documents'],
  ['MULTILINGUAL', 'Multilingual'],
]

export default function DatasetsPage() {
  const queryClient = useQueryClient()
  const datasets = useQuery({ queryKey: ['eval-datasets'], queryFn: evaluation.listDatasets })
  const [selected, setSelected] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const create = useMutation({
    mutationFn: () => evaluation.createDataset(name.trim(), description),
    onSuccess: (d) => {
      setName('')
      setDescription('')
      setSelected(d.id)
      queryClient.invalidateQueries({ queryKey: ['eval-datasets'] })
    },
  })
  const current = datasets.data?.find((d) => d.id === selected) ?? null

  return (
    <>
      <p className="muted">
        <Link to="/evaluation">Evaluation</Link> / Datasets
      </p>
      <PageHeader title="Evaluation datasets" description="Golden questions with their expected answers and sources. A version is frozen once a run has used it." />
      <form
        className="toolbar"
        onSubmit={(e: FormEvent) => {
          e.preventDefault()
          create.mutate()
        }}
      >
        <input placeholder="New dataset name, e.g. hr-basics" value={name} onChange={(e) => setName(e.target.value)} aria-label="Dataset name" />
        <input placeholder="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} aria-label="Description" />
        <button className="btn btn-primary" disabled={!name.trim() || create.isPending}>
          Create
        </button>
      </form>
      <ErrorMessage error={create.error ?? datasets.error} />
      {datasets.isPending && <Loading />}
      {datasets.data?.length === 0 && <EmptyState>No datasets yet.</EmptyState>}
      <div className="table-wrap">
        <table>
          <tbody>
            {datasets.data?.map((d) => (
              <tr key={d.id} className={d.id === selected ? 'selected' : undefined}>
                <td>
                  <strong>{d.name}</strong> v{d.version} {d.frozen && <StatusBadge label="frozen" tone="neutral" />}
                  <br />
                  <span className="muted small">{d.description}</span>
                </td>
                <td>{d.case_count} cases</td>
                <td className="row-actions">
                  <button type="button" className="btn btn-small" onClick={() => setSelected(d.id === selected ? null : d.id)}>
                    {d.id === selected ? 'Close' : 'Open'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {current && <DatasetEditor key={current.id} dataset={current} onVersion={(d) => setSelected(d.id)} />}
    </>
  )
}

function DatasetEditor({ dataset, onVersion }: { dataset: Dataset; onVersion: (d: Dataset) => void }) {
  const queryClient = useQueryClient()
  const file = useRef<HTMLInputElement>(null)
  const cases = useQuery({ queryKey: ['eval-cases', dataset.id], queryFn: () => evaluation.listCases(dataset.id) })
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['eval-cases', dataset.id] })
    queryClient.invalidateQueries({ queryKey: ['eval-datasets'] })
  }
  const [form, setForm] = useState({ question: '', expected_answer: '', expected_sources: '', case_type: 'FACTUAL' as CaseType, as_groups: '' })
  const add = useMutation({
    mutationFn: () =>
      evaluation.addCase(dataset.id, {
        question: form.question.trim(),
        expected_answer: form.expected_answer.trim() || null,
        expected_sources: form.expected_sources.split(';').map((s) => s.trim()).filter(Boolean),
        case_type: form.case_type,
        metadata_json: form.as_groups.trim() ? { as_groups: form.as_groups.split(';').map((s) => s.trim()).filter(Boolean) } : {},
      }),
    onSuccess: () => {
      setForm({ ...form, question: '', expected_answer: '', expected_sources: '' })
      refresh()
    },
  })
  const remove = useMutation({ mutationFn: evaluation.deleteCase, onSuccess: refresh })
  const version = useMutation({ mutationFn: () => evaluation.newDatasetVersion(dataset.id), onSuccess: (d) => { refresh(); onVersion(d) } })
  const failures = useMutation({ mutationFn: () => evaluation.versionFromFailures(dataset.id), onSuccess: (d) => { refresh(); onVersion(d) } })
  const [importError, setImportError] = useState<string | null>(null)

  async function importFile(chosen: File | undefined) {
    if (!chosen) return
    setImportError(null)
    try {
      await evaluation.importCases(dataset.id, chosen)
      refresh()
    } catch (err) {
      setImportError(err instanceof ApiError ? Object.entries(err.details).map(([k, v]) => `${k}: ${v}`).join(' · ') || err.message : errorMessage(err))
    } finally {
      if (file.current) file.current.value = ''
    }
  }

  return (
    <section className="panel">
      <div className="page-header">
        <h2>
          {dataset.name} v{dataset.version}
        </h2>
        <div className="actions">
          <button type="button" className="btn btn-small" onClick={() => version.mutate()}>
            New version
          </button>
          <button type="button" className="btn btn-small" onClick={() => failures.mutate()}>
            New version + resolved failures
          </button>
        </div>
      </div>
      <ErrorMessage error={version.error ?? failures.error ?? remove.error} />
      {dataset.frozen && <p className="alert alert-warn">This version was used by a run, so it can't change. Create a new version to edit cases.</p>}
      {!dataset.frozen && (
        <>
          <form
            className="form-grid"
            onSubmit={(e: FormEvent) => {
              e.preventDefault()
              add.mutate()
            }}
          >
            <label>
              Question
              <input value={form.question} onChange={(e) => setForm({ ...form, question: e.target.value })} />
            </label>
            <label>
              Type
              <select value={form.case_type} onChange={(e) => setForm({ ...form, case_type: e.target.value as CaseType })}>
                {CASE_TYPES.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Expected answer (key facts)
              <input value={form.expected_answer} onChange={(e) => setForm({ ...form, expected_answer: e.target.value })} />
            </label>
            <label>
              {form.case_type === 'ACCESS' ? 'Forbidden documents' : 'Expected source documents'} (file names, separated by ;)
              <input value={form.expected_sources} onChange={(e) => setForm({ ...form, expected_sources: e.target.value })} />
            </label>
            {form.case_type === 'ACCESS' && (
              <label>
                Ask as members of (groups, separated by ;)
                <input value={form.as_groups} onChange={(e) => setForm({ ...form, as_groups: e.target.value })} />
              </label>
            )}
            {add.error instanceof ApiError && <p className="alert alert-error">{add.error.message}</p>}
            <div className="actions">
              <button className="btn btn-primary" disabled={!form.question.trim() || add.isPending}>
                Add case
              </button>
              <button type="button" className="btn" onClick={() => file.current?.click()}>
                Import CSV / JSON
              </button>
              <input ref={file} type="file" accept=".csv,.json" hidden aria-label="Cases file" onChange={(e) => importFile(e.target.files?.[0])} />
              <span className="muted small">CSV columns: question, expected_answer, expected_sources, case_type, as_groups</span>
            </div>
            {importError && <p className="alert alert-error">{importError}</p>}
          </form>
        </>
      )}
      {cases.isPending && <Loading />}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Question</th>
              <th>Type</th>
              <th>Expected</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {cases.data?.map((c) => (
              <tr key={c.id}>
                <td>{c.question}</td>
                <td>{c.case_type}</td>
                <td>
                  {c.expected_answer && <div>{c.expected_answer}</div>}
                  {c.expected_sources.length > 0 && <div className="muted small">{c.expected_sources.join('; ')}</div>}
                  {Array.isArray(c.metadata_json.as_groups) && <div className="muted small">as: {(c.metadata_json.as_groups as string[]).join('; ')}</div>}
                </td>
                <td>
                  {!dataset.frozen && (
                    <ConfirmButton label="Delete" title="Delete this case?" message={c.question} danger onConfirm={() => remove.mutate(c.id)} />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
