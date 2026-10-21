import { readSse, type SseEvent } from '../lib/sse'
import { csrfToken } from '../lib/csrf'
import { api, API_BASE, ApiError, authEvents, type Page } from './client'
import type { ChunkView, FailureCase, Run } from './types'

/** POST /ask/ and hand every server-sent event to onEvent until the stream ends. */
export async function ask(question: string, onEvent: (event: SseEvent) => void, signal?: AbortSignal): Promise<void> {
  const headers = new Headers({ 'Content-Type': 'application/json', Accept: 'text/event-stream' })
  const token = csrfToken()
  if (token) headers.set('X-CSRFToken', token)
  const response = await fetch(`${API_BASE}/ask/`, { method: 'POST', headers, body: JSON.stringify({ question }), credentials: 'same-origin', signal })
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => null)
    if (response.status === 401) authEvents.dispatchEvent(new Event('unauthorized'))
    throw new ApiError(response.status, body)
  }
  for await (const event of readSse(response.body)) onEvent(event)
}

export const myRuns = (page = 1) => api.get<Page<Run>>(`/runs/?mine=1&page=${page}`)
export const getRun = (id: string) => api.get<Run>(`/runs/${id}/`)
export const getChunk = (id: string) => api.get<ChunkView>(`/chunks/${id}/`)
export const sendFeedback = (answerId: string, rating: number, feedback_text: string, problem: string) =>
  api.post(`/answers/${answerId}/feedback/`, { rating, feedback_text, problem })

export const listFailureCases = (status = '', page = 1) =>
  api.get<Page<FailureCase>>(`/failure-cases/?page=${page}${status ? `&review_status=${status}` : ''}`)
export const updateFailureCase = (id: string, data: Partial<Pick<FailureCase, 'review_status' | 'root_cause' | 'resolution_notes' | 'failure_type'>>) =>
  api.patch<FailureCase>(`/failure-cases/${id}/`, data)
