import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { ApiError } from '../../api/client'
import * as pipelines from '../../api/pipelines'
import type { Component, PipelineVersion } from '../../api/types'
import { useCan } from '../../auth/session'
import { ConfirmButton } from '../../components/ConfirmButton'
import { ErrorMessage, Loading, PageHeader } from '../../components/Feedback'
import { JsonEditor } from '../../components/JsonEditor'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../lib/format'
import { INGESTION_TYPES, VERSION_TONE } from './status'

export default function VersionPage() {
  const { versionId = '' } = useParams()
  const version = useQuery({ queryKey: ['pipeline-version', versionId], queryFn: () => pipelines.getVersion(versionId) })
  const components = useQuery({ queryKey: ['components'], queryFn: pipelines.listComponents })
  const all = useQuery({ queryKey: ['pipelines'], queryFn: pipelines.listPipelines })

  if (version.isPending) return <Loading />
  if (version.error || !version.data) return <ErrorMessage error={version.error} />
  const v = version.data
  const pipeline = all.data?.find((p) => p.id === v.pipeline)
  const hasPublished = pipeline?.versions.some((x) => x.status !== 'DRAFT') ?? true

  return (
    <>
      <p className="muted">
        <Link to="/pipelines">Pipelines</Link> / {v.pipeline_name}
      </p>
      <PageHeader
        title={`${v.pipeline_name} v${v.version_number}`}
        description={`Author: ${v.created_by ?? 'system'} · Published: ${formatDateTime(v.published_at)}${v.published_by ? ` by ${v.published_by}` : ''}`}
        actions={<VersionActions version={v} hasPublished={hasPublished} />}
      />
      <p>
        <StatusBadge label={v.status} tone={VERSION_TONE[v.status]} />
        {v.status !== 'DRAFT' && <span className="muted"> This version is frozen. Clone it to change anything.</span>}
      </p>
      {components.data && <StepsEditor key={v.id + v.steps.map((s) => s.id).join()} version={v} components={components.data} />}
      <SettingsPanel version={v} />
    </>
  )
}

function VersionActions({ version, hasPublished }: { version: PipelineVersion; hasPublished: boolean }) {
  const can = useCan()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const clone = useMutation({
    mutationFn: () => pipelines.cloneVersion(version.id),
    onSuccess: (draft) => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] })
      navigate(`/pipelines/${draft.pipeline}/versions/${draft.id}`)
    },
  })
  const publish = useMutation({
    mutationFn: () => pipelines.publishInitial(version.id),
    onSuccess: (updated) => {
      queryClient.setQueryData(['pipeline-version', version.id], updated)
      queryClient.invalidateQueries({ queryKey: ['pipelines'] })
    },
  })
  return (
    <div className="actions">
      {can('pipelines.edit') && (
        <button type="button" className="btn" onClick={() => clone.mutate()} disabled={clone.isPending}>
          Clone to new draft
        </button>
      )}
      {can('releases.approve') && version.status === 'DRAFT' && !hasPublished && (
        <ConfirmButton
          label="Publish first version"
          title={`Publish ${version.pipeline_name} v${version.version_number}?`}
          message="It becomes the live pipeline for new uploads and is frozen from then on. Later versions are released through evaluation and approval."
          onConfirm={() => publish.mutate()}
        />
      )}
      <ErrorMessage error={clone.error ?? publish.error} />
    </div>
  )
}

type DraftStep = { key: string; component: string; config: Record<string, unknown>; is_enabled: boolean }

function StepsEditor({ version, components }: { version: PipelineVersion; components: Component[] }) {
  const can = useCan()
  const queryClient = useQueryClient()
  const editable = version.status === 'DRAFT' && can('pipelines.edit')
  const ingestion = components.filter((c) => INGESTION_TYPES.has(c.component_type))
  const describe = (key: string) => components.find((c) => c.key === key)?.description ?? ''
  const [steps, setSteps] = useState<DraftStep[]>(() =>
    version.steps.map((s) => ({ key: s.id, component: s.component, config: s.config, is_enabled: s.is_enabled })),
  )
  const save = useMutation({
    mutationFn: () => pipelines.replaceSteps(version.id, steps.map(({ component, config, is_enabled }) => ({ component, config, is_enabled }))),
    onSuccess: (updated) => queryClient.setQueryData(['pipeline-version', version.id], updated),
  })
  const fieldErrors = (index: number) => {
    if (!(save.error instanceof ApiError)) return []
    return Object.entries(save.error.details)
      .filter(([field]) => field.startsWith(`steps.${index}.`))
      .flatMap(([field, messages]) => (messages as string[]).map((m) => `${field.replace(`steps.${index}.`, '')}: ${m}`))
  }
  const update = (index: number, change: Partial<DraftStep>) => setSteps(steps.map((s, i) => (i === index ? { ...s, ...change } : s)))
  const move = (index: number, by: number) => {
    const next = [...steps]
    const [item] = next.splice(index, 1)
    next.splice(index + by, 0, item)
    setSteps(next)
  }

  return (
    <section className="panel">
      <h2>Ingestion steps</h2>
      <p className="muted">Each enabled step runs in order on every uploaded document.</p>
      <ol className="steps">
        {steps.map((step, index) => (
          <li key={step.key} className={step.is_enabled ? 'step' : 'step step-off'}>
            <div className="step-head">
              <span className="step-no">{index + 1}</span>
              {editable ? (
                <select value={step.component} aria-label={`Component of step ${index + 1}`} onChange={(e) => update(index, { component: e.target.value, config: {} })}>
                  {ingestion.map((c) => (
                    <option key={c.key} value={c.key}>
                      {c.key}
                    </option>
                  ))}
                </select>
              ) : (
                <code>{step.component}</code>
              )}
              <span className="muted step-desc">{describe(step.component)}</span>
              <label className="check">
                <input type="checkbox" checked={step.is_enabled} disabled={!editable} onChange={(e) => update(index, { is_enabled: e.target.checked })} />
                enabled
              </label>
              {editable && (
                <span className="row-actions">
                  <button type="button" className="btn btn-small" disabled={index === 0} onClick={() => move(index, -1)} aria-label="Move up">
                    ↑
                  </button>
                  <button type="button" className="btn btn-small" disabled={index === steps.length - 1} onClick={() => move(index, 1)} aria-label="Move down">
                    ↓
                  </button>
                  <button type="button" className="btn btn-small btn-danger" onClick={() => setSteps(steps.filter((_, i) => i !== index))}>
                    Remove
                  </button>
                </span>
              )}
            </div>
            <JsonEditor
              key={step.component}
              label={`Settings of step ${index + 1}`}
              value={step.config}
              readOnly={!editable}
              rows={Math.min(8, Math.max(2, Object.keys(step.config).length + 2))}
              onChange={(config) => update(index, { config })}
              errors={fieldErrors(index)}
            />
          </li>
        ))}
      </ol>
      {editable && (
        <div className="actions">
          <button
            type="button"
            className="btn"
            onClick={() => setSteps([...steps, { key: crypto.randomUUID(), component: ingestion[0]?.key ?? '', config: {}, is_enabled: true }])}
          >
            Add step
          </button>
          <button type="button" className="btn btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>
            Save steps
          </button>
          {save.isSuccess && <span className="muted">Saved.</span>}
          {save.error instanceof ApiError && save.error.code === 'validation_error' && <span className="field-error">Some steps have errors — see below each step.</span>}
          {save.error && !(save.error instanceof ApiError && save.error.code === 'validation_error') && <ErrorMessage error={save.error} />}
        </div>
      )}
    </section>
  )
}

function SettingsPanel({ version }: { version: PipelineVersion }) {
  const can = useCan()
  const queryClient = useQueryClient()
  const editable = version.status === 'DRAFT' && can('pipelines.edit')
  const retrieval = useQuery({ queryKey: ['retrieval-definitions'], queryFn: pipelines.listRetrievalDefinitions })
  const generation = useQuery({ queryKey: ['generation-definitions'], queryFn: pipelines.listGenerationDefinitions })
  const [retrievalId, setRetrievalId] = useState(version.retrieval_definition.id)
  const [generationId, setGenerationId] = useState(version.generation_definition.id)
  const save = useMutation({
    mutationFn: () => pipelines.updateVersion(version.id, { retrieval_definition_id: retrievalId, generation_definition_id: generationId }),
    onSuccess: (updated) => queryClient.setQueryData(['pipeline-version', version.id], updated),
  })
  const r = retrieval.data?.find((d) => d.id === retrievalId)
  const g = generation.data?.find((d) => d.id === generationId)

  return (
    <section className="panel">
      <h2>Retrieval and answer settings</h2>
      <div className="grid-2">
        <div>
          <label>
            Retrieval settings
            <select value={retrievalId} disabled={!editable} onChange={(e) => setRetrievalId(e.target.value)}>
              {retrieval.data?.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
          {r && (
            <JsonEditor
              key={r.id}
              label="Retrieval settings (read only)"
              readOnly
              rows={12}
              value={{ dense: r.dense_config, bm25: r.bm25_config, fusion: r.fusion_config, reranker: r.reranker_config, context: r.context_config }}
            />
          )}
        </div>
        <div>
          <label>
            Answer settings
            <select value={generationId} disabled={!editable} onChange={(e) => setGenerationId(e.target.value)}>
              {generation.data?.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.model_name})
                </option>
              ))}
            </select>
          </label>
          {g && (
            <JsonEditor
              key={g.id}
              label="Answer settings (read only)"
              readOnly
              rows={12}
              value={{ model: g.model_name, generation: g.generation_config, citations: g.citation_config, abstention: g.abstention_config }}
            />
          )}
        </div>
      </div>
      {g && (
        <details>
          <summary>Prompt template</summary>
          <pre className="prompt">{g.prompt_template}</pre>
        </details>
      )}
      {editable && (
        <div className="actions">
          <button type="button" className="btn btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>
            Save settings
          </button>
          {save.isSuccess && <span className="muted">Saved.</span>}
          <ErrorMessage error={save.error} />
        </div>
      )}
    </section>
  )
}
