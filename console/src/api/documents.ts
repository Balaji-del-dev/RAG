import { api, API_BASE, ApiError, type Page } from './client'
import { csrfToken } from '../lib/csrf'
import type { DocumentDetail, DocumentRow, Job, JobDetail, UploadResult } from './types'

export type DocumentFilters = { search?: string; status?: string; type?: string; group?: string; page?: number }

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== '') search.set(key, String(value))
  const text = search.toString()
  return text ? `?${text}` : ''
}

export const listDocuments = (filters: DocumentFilters = {}) => api.get<Page<DocumentRow>>(`/documents/${query(filters)}`)

export const getDocument = (id: string) => api.get<DocumentDetail>(`/documents/${id}/`)

export const deleteDocument = (id: string) => api.delete(`/documents/${id}/`)

export const setDocumentAccess = (id: string, access_group_ids: string[]) =>
  api.put<DocumentDetail>(`/documents/${id}/access/`, { access_group_ids })

export const downloadUrl = (id: string, version?: number) => `${API_BASE}/documents/${id}/download/${version ? `?version=${version}` : ''}`

/** Multipart upload with progress (fetch has no upload progress events, so this uses XMLHttpRequest). */
export function uploadWithProgress<T>(path: string, form: FormData, onProgress: (fraction: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}${path}`)
    xhr.withCredentials = true
    xhr.setRequestHeader('Accept', 'application/json')
    const token = csrfToken()
    if (token) xhr.setRequestHeader('X-CSRFToken', token)
    xhr.upload.onprogress = (event) => event.lengthComputable && onProgress(event.loaded / event.total)
    xhr.onerror = () => reject(new TypeError('network error'))
    xhr.onload = () => {
      let body: unknown
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        body = null
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as T)
      else reject(new ApiError(xhr.status, body as never))
    }
    xhr.send(form)
  })
}

export function uploadDocument(file: File, groupIds: string[], onProgress: (fraction: number) => void) {
  const form = new FormData()
  form.append('file', file)
  for (const id of groupIds) form.append('access_group_ids', id)
  return uploadWithProgress<UploadResult>('/documents/', form, onProgress)
}

export function uploadNewVersion(id: string, file: File, onProgress: (fraction: number) => void) {
  const form = new FormData()
  form.append('file', file)
  return uploadWithProgress<DocumentDetail>(`/documents/${id}/versions/`, form, onProgress)
}

export const listJobs = (documentId: string) => api.get<Page<Job>>(`/jobs/${query({ document: documentId })}`)
export const getJob = (id: string) => api.get<JobDetail>(`/jobs/${id}/`)
export const retryJob = (id: string) => api.post<JobDetail>(`/jobs/${id}/retry/`)
export const cancelJob = (id: string) => api.post<JobDetail>(`/jobs/${id}/cancel/`)
