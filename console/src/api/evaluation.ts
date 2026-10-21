import { api, type Page } from './client'
import { uploadWithProgress } from './documents'
import type { AuditEvent, Dataset, EvalCase, EvalRun, EvalRunDetail } from './types'

export const listDatasets = () => api.get<Dataset[]>('/eval/datasets/')
export const createDataset = (name: string, description: string) => api.post<Dataset>('/eval/datasets/', { name, description })
export const listCases = (datasetId: string) => api.get<EvalCase[]>(`/eval/datasets/${datasetId}/cases/`)
export const addCase = (datasetId: string, data: Omit<EvalCase, 'id' | 'dataset'>) => api.post<EvalCase>(`/eval/datasets/${datasetId}/cases/`, data)
export const deleteCase = (id: string) => api.delete(`/eval/cases/${id}/`)
export const newDatasetVersion = (id: string) => api.post<Dataset>(`/eval/datasets/${id}/new-version/`)
export const versionFromFailures = (id: string) => api.post<Dataset>(`/eval/datasets/${id}/cases/from-failures/`)

export function importCases(id: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  return uploadWithProgress<EvalCase[]>(`/eval/datasets/${id}/import/`, form, () => undefined)
}

export type Candidate = { index_generation_id: string; generation_number: number; status: string; pipeline_version_id: string; label: string }
export const listCandidates = () => api.get<Candidate[]>('/eval/candidates/')
export const listRuns = () => api.get<EvalRun[]>('/eval/runs/')
export const getRun = (id: string) => api.get<EvalRunDetail>(`/eval/runs/${id}/`)
export const startRun = (data: { dataset_id: string; pipeline_version_id: string; index_generation_id: string; use_llm_judge: boolean }) =>
  api.post<EvalRun>('/eval/runs/', data)
export const approveRun = (id: string) => api.post<EvalRun>(`/eval/runs/${id}/approve/`)

export type AuditFilters = { actor?: string; event_type?: string; since?: string; until?: string; page?: number }
export function listAuditEvents(filters: AuditFilters) {
  const search = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) if (v !== undefined && v !== '') search.set(k, String(v))
  return api.get<Page<AuditEvent>>(`/audit-events/?${search}`)
}
