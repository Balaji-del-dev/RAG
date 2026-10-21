import { api } from './client'
import type { Generation, GenerationDetail } from './types'

export const listGenerations = () => api.get<Generation[]>('/index-generations/')
export const getGeneration = (id: string) => api.get<GenerationDetail>(`/index-generations/${id}/`)
export const buildGeneration = (pipeline_version_id: string) => api.post<GenerationDetail>('/index-generations/', { pipeline_version_id })
export const validateGeneration = (id: string) => api.post<{ queued: boolean }>(`/index-generations/${id}/validate/`)
export const publishGeneration = (id: string) => api.post<GenerationDetail>(`/index-generations/${id}/publish/`)
export const rollbackGeneration = (id: string) => api.post<GenerationDetail>(`/index-generations/${id}/rollback/`)
