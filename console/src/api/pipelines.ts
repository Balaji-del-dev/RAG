import { api } from './client'
import type { Component, GenerationDefinition, Pipeline, PipelineVersion, RetrievalDefinition } from './types'

export const listPipelines = () => api.get<Pipeline[]>('/pipelines/')

export const getVersion = (id: string) => api.get<PipelineVersion>(`/pipeline-versions/${id}/`)

export const updateVersion = (id: string, data: { config_json?: object; retrieval_definition_id?: string; generation_definition_id?: string }) =>
  api.patch<PipelineVersion>(`/pipeline-versions/${id}/`, data)

export type StepInput = { component: string; config: Record<string, unknown>; is_enabled: boolean }

export const replaceSteps = (id: string, steps: StepInput[]) => api.put<PipelineVersion>(`/pipeline-versions/${id}/steps/`, { steps })

export const cloneVersion = (id: string) => api.post<PipelineVersion>(`/pipeline-versions/${id}/clone/`)

export const publishInitial = (id: string) => api.post<PipelineVersion>(`/pipeline-versions/${id}/publish-initial/`)

export const listComponents = () => api.get<Component[]>('/components/')

export const listRetrievalDefinitions = () => api.get<RetrievalDefinition[]>('/retrieval-definitions/')

export const listGenerationDefinitions = () => api.get<GenerationDefinition[]>('/generation-definitions/')
