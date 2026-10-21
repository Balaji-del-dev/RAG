// Response types — keep in step with /api/schema/ (docs/plan/04-api.md).

export type Me = {
  id: string
  username: string
  email: string
  display_name: string
  auth_source: 'LOCAL' | 'LDAP'
  mfa_enabled: boolean
  roles: string[]
  permissions: string[]
  access_groups: string[]
  /** A 6-digit code must still be entered for this session. */
  mfa_required: boolean
  /** An Admin who has not set up an authenticator app yet. */
  mfa_setup_required: boolean
}

export type LoginResult = { mfa_required: boolean; user: Me }

export type SessionRow = {
  id: string
  username: string
  ip_address: string | null
  user_agent: string
  created_at: string
  last_seen_at: string
  expires_at: string
  revoked_at: string | null
  is_active: boolean
  is_current: boolean
}

export type NamedRef = { id: string; name: string }

export type AdminUser = {
  id: string
  username: string
  email: string
  display_name: string
  auth_source: 'LOCAL' | 'LDAP'
  is_active: boolean
  is_locked: boolean
  locked_until: string | null
  failed_login_count: number
  mfa_enabled: boolean
  last_login: string | null
  created_at: string
  roles: NamedRef[]
  access_groups: NamedRef[]
}

export type Role = { id: string; name: string; description: string; is_system: boolean; permissions: string[] }

export type AccessGroup = { id: string; name: string; description: string; created_at: string; member_count?: number }

export type MfaSetup = { otpauth_url: string; qr_svg: string }

export type Health = { status: 'ok' | 'degraded'; services: Record<string, 'up' | 'down'> }

// ---- pipelines (registry)

export type NamedId = { id: string; name: string }

export type PipelineStep = {
  id: string
  step_order: number
  component: string
  component_type: string
  description: string
  config: Record<string, unknown>
  is_enabled: boolean
}

export type VersionStatus = 'DRAFT' | 'PUBLISHED' | 'RETIRED'

export type PipelineVersion = {
  id: string
  pipeline: string
  pipeline_name: string
  version_number: number
  status: VersionStatus
  config_json: Record<string, unknown>
  retrieval_definition: NamedId
  generation_definition: NamedId
  created_by: string | null
  published_at: string | null
  published_by: string | null
  steps: PipelineStep[]
}

export type VersionSummary = { id: string; version_number: number; status: VersionStatus; created_by: string | null; published_at: string | null }

export type Pipeline = { id: string; name: string; description: string | null; is_active: boolean; created_at: string; versions: VersionSummary[] }

export type Component = { id: string; key: string; component_type: string; description: string; config_schema: Record<string, unknown>; is_active: boolean }

export type RetrievalDefinition = {
  id: string
  name: string
  dense_config: Record<string, unknown>
  bm25_config: Record<string, unknown>
  fusion_config: Record<string, unknown>
  reranker_config: Record<string, unknown>
  context_config: Record<string, unknown>
  in_use: boolean
}

export type GenerationDefinition = {
  id: string
  name: string
  model: string
  model_name: string
  prompt_template: string
  generation_config: Record<string, unknown>
  citation_config: Record<string, unknown>
  abstention_config: Record<string, unknown>
  in_use: boolean
}

// ---- documents, jobs, indexes

export type DocumentStatus = 'PENDING' | 'ACTIVE' | 'FAILED' | 'DELETED'
export type VersionState =
  | 'UPLOADED' | 'VALIDATING' | 'QUEUED' | 'PROCESSING' | 'INDEXING' | 'VALIDATING_INDEX'
  | 'PUBLISHED' | 'FAILED' | 'SUPERSEDED' | 'DELETED'

export type DocumentVersionInfo = { id: string; version_number: number; status: VersionState; file_size: number; content_sha256: string }

export type JobStatus = 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'RETRY' | 'CANCELLED'

export type JobSummary = {
  id: string
  job_type: 'INGEST' | 'REPROCESS'
  status: JobStatus
  attempt_count: number
  created_at: string
  started_at: string | null
  completed_at: string | null
  error_message: string | null
}

export type DocumentRow = {
  id: string
  filename: string
  file_extension: string
  mime_type: string
  lifecycle_status: DocumentStatus
  current_version: DocumentVersionInfo | null
  access_groups: NamedId[]
  created_by: string
  created_at: string
  updated_at: string
}

export type DocumentDetail = DocumentRow & { versions: DocumentVersionInfo[]; latest_job: JobSummary | null }

export type UploadResult = { duplicate: boolean; document: DocumentDetail }

export type StepRun = {
  id: string
  step_name: string
  status: 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'SKIPPED'
  attempt: number
  input_summary: Record<string, unknown>
  output_summary: Record<string, unknown> | null
  duration_ms: number | null
  error_message: string | null
}

export type Job = JobSummary & { document_id: string; filename: string; version_number: number; pipeline_version: string }
export type JobDetail = Job & { steps: StepRun[] }

export type GenerationStatus = 'BUILDING' | 'VALIDATING' | 'PUBLISHED' | 'RETIRED' | 'FAILED'

export type Validation = {
  id: number | string
  validation_type: string
  status: 'PASSED' | 'FAILED'
  expected_count: number | null
  actual_count: number | null
  details_json: Record<string, unknown>
}

export type Generation = {
  id: string
  generation_number: number
  pipeline_version: string
  pipeline_version_label: string
  qdrant_collection: string
  opensearch_index: string
  status: GenerationStatus
  published_at: string | null
  counts: { chunks: number; documents: number; removed: number }
  validated: boolean
}

export type GenerationDetail = Generation & { validations: Validation[]; build_jobs: JobSummary[] }

// ---- chat (retrieval)

export type Citation = {
  n: number
  chunk_id: string
  document_id: string
  filename: string
  page_start: number | null
  page_end: number | null
  section_path: string
}

export type AnswerStatus = 'VALIDATED' | 'REPAIRED' | 'ABSTAINED' | 'REJECTED'

export type Answer = {
  id: string
  answer_text: string | null
  citation_data: Citation[]
  status: AnswerStatus
  latency_ms: number
  token_usage_json: Record<string, number>
  prompt_version: string
  my_feedback: { rating: number; feedback_text: string | null } | null
}

export type RunStatus = 'RUNNING' | 'ANSWERED' | 'ABSTAINED' | 'REJECTED' | 'FAILED'

export type Run = { id: string; request_id: string; username: string; query_text: string; status: RunStatus; latency_ms: number; created_at: string; answer: Answer | null }

export type ChunkView = {
  id: string
  text_content: string
  page_start: number | null
  page_end: number | null
  section_path: string | null
  document_id: string
  filename: string
  version_number: number
}

export type FailureCase = {
  id: string
  retrieval_run: string
  question: string
  asked_by: string
  asked_at: string
  run_status: RunStatus
  failure_type: string
  root_cause: string | null
  review_status: 'OPEN' | 'IN_REVIEW' | 'RESOLVED' | 'WONT_FIX'
  resolution_notes: string | null
}

// ---- evaluation and audit

export type Dataset = { id: string; name: string; version: number; description: string | null; case_count: number; frozen: boolean }

export type CaseType = 'FACTUAL' | 'MULTI_HOP' | 'TABLE' | 'NO_ANSWER' | 'ACCESS' | 'MULTILINGUAL'

export type EvalCase = {
  id: string
  dataset: string
  question: string
  expected_answer: string | null
  expected_sources: string[]
  case_type: CaseType
  metadata_json: Record<string, unknown>
}

export type Gate = { metric: string; value: number; baseline: number | null; min: number | null; max_drop: number | null; passed: boolean }

export type EvalRunStatus = 'QUEUED' | 'RUNNING' | 'PASSED' | 'FAILED' | 'ERROR'

export type EvalRun = {
  id: string
  dataset: string
  dataset_label: string
  pipeline_version: string
  pipeline_version_label: string
  pipeline_version_author: string | null
  index_generation: string
  generation_number: number
  status: EvalRunStatus
  summary_json: {
    metrics?: Record<string, number>
    baseline?: Record<string, number>
    baseline_run_id?: string | null
    gates?: Gate[]
    passed?: boolean
    use_llm_judge?: boolean
    started_by?: string
    cases?: number
    error?: string
    judge_errors?: number
  }
  started_at: string
  completed_at: string | null
  approved_by: string | null
  is_live: boolean
}

export type EvalResult = {
  id: string
  evaluation_case: string
  question: string
  case_type: CaseType
  metric_name: string
  score: number
  passed: boolean
  details_json: Record<string, unknown>
}

export type EvalRunDetail = EvalRun & { results: EvalResult[] }

export type AuditEvent = {
  id: number
  created_at: string
  actor: string
  actor_user: string | null
  event_type: string
  entity_type: string
  entity_id: string | null
  ip_address: string | null
  details_json: Record<string, unknown>
}
