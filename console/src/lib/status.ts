import type { Tone } from '../components/StatusBadge'

/** One colour per lifecycle status (docs/plan/03-database.md §4). */
export const STATUS_TONE: Record<string, Tone> = {
  ACTIVE: 'ok', PUBLISHED: 'ok', SUCCEEDED: 'ok', PASSED: 'ok', INDEXED: 'ok',
  PENDING: 'info', QUEUED: 'info', PROCESSING: 'info', INDEXING: 'info', VALIDATING_INDEX: 'info', RUNNING: 'info',
  BUILDING: 'info', VALIDATING: 'info', UPLOADED: 'info', RETRY: 'warn',
  FAILED: 'bad', CANCELLED: 'neutral', DELETED: 'neutral', SUPERSEDED: 'neutral', RETIRED: 'neutral', SKIPPED: 'neutral',
  DRAFT: 'info',
}

export const toneFor = (status: string): Tone => STATUS_TONE[status] ?? 'neutral'

/** Statuses that will change by themselves soon, so the page keeps polling. */
export const IN_PROGRESS = new Set(['UPLOADED', 'VALIDATING', 'QUEUED', 'PROCESSING', 'INDEXING', 'RUNNING', 'RETRY'])

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
