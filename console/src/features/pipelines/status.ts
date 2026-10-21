import type { VersionStatus } from '../../api/types'
import type { Tone } from '../../components/StatusBadge'

export const VERSION_TONE: Record<VersionStatus, Tone> = { DRAFT: 'info', PUBLISHED: 'ok', RETIRED: 'neutral' }

/** Component types that can be ingestion steps (backend: apps/registry/components.py). */
export const INGESTION_TYPES = new Set([
  'READER', 'PARSER', 'OCR', 'CLEANER', 'STRUCTURE', 'ENRICHER', 'CHUNKER', 'CHUNK_CHECK', 'PERSIST', 'EMBEDDER',
])
