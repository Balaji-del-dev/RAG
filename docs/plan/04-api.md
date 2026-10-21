# 04 · API contract

This is the contract between the console ([02-frontend.md](02-frontend.md)) and the backend ([01-backend.md](01-backend.md)). drf-spectacular generates the exact schema from the code at `/api/schema/`; this page is the plan it must match.

## 1. Rules for every endpoint

| Rule | Detail |
|---|---|
| Base path | `/api/v1/` |
| Format | JSON (`application/json`); uploads use `multipart/form-data`; `/ask/` streams `text/event-stream` |
| Authentication | Session cookie. **Every endpoint needs a signed-in user**, except `auth/csrf/`, `auth/login/`, `auth/mfa/verify/` and `health/` |
| CSRF | `X-CSRFToken` header on every `POST`, `PUT`, `PATCH`, `DELETE` |
| Authorization | Each endpoint lists its permission below; without it the answer is `403`. Documents outside the user's access groups give `404` |
| Pagination | `?page=1&page_size=25` (max 100) → `{ "count", "next", "previous", "results": [...] }` |
| Filtering and sorting | query parameters, for example `?status=FAILED&ordering=-created_at` |
| IDs | UUID strings |
| Times | ISO 8601 in UTC, for example `2026-10-20T09:30:00Z` |
| Rate limits | 10 questions per minute per user on `/ask/`; 5 sign-in attempts per minute per IP; 120 other requests per minute per user |
| Request ID | Every response has an `X-Request-ID` header; it is also in the logs and in `retrieval_runs.request_id` |

**Error format.** Every error uses the same shape:

```json
{
  "error": {
    "code": "permission_denied",
    "message": "You don't have permission to upload documents.",
    "details": {}
  },
  "request_id": "6f1c…"
}
```

| Status | `code` examples | When |
|---|---|---|
| 400 | `validation_error` | Bad input. `details` maps each field to its messages |
| 401 | `not_authenticated`, `session_expired` | Not signed in, or the session expired or was revoked |
| 403 | `permission_denied`, `csrf_failed`, `mfa_required` | Signed in but not allowed |
| 404 | `not_found` | Does not exist, **or** is outside the user's access groups |
| 409 | `conflict`, `duplicate_document`, `version_published` | The current state does not allow the action |
| 413 | `file_too_large` | Upload over the size limit |
| 415 | `unsupported_file_type` | Extension not allowed, or the sniffed MIME type does not match it |
| 423 | `account_locked` | Too many failed sign-ins |
| 429 | `throttled` | Rate limit hit (`Retry-After` header) |
| 503 | `service_unavailable`, `llm_busy` | A backing service is down, or the model is busy |

## 2. Endpoints

**Permission** = the codename the user's roles must include. "signed in" = any active user.

### 2.1 Auth and my account (`accounts`)

| Method | Path | Permission | Does |
|---|---|---|---|
| GET | `auth/csrf/` | none | Sets the `csrftoken` cookie |
| POST | `auth/login/` | none | `{username, password}` → sets the session cookie; returns `{mfa_required}`. A wrong password gives `400` with a generic message; locked gives `423` |
| POST | `auth/mfa/verify/` | half-signed-in | `{code}` → marks the session MFA-verified |
| POST | `auth/logout/` | signed in | Ends this session |
| GET | `auth/me/` | signed in | `{id, username, display_name, roles[], permissions[], access_groups[], mfa_enabled}` |
| GET | `auth/sessions/` | signed in | My active sessions |
| POST | `auth/sessions/revoke-all/` | signed in | Signs me out everywhere |
| POST | `auth/mfa/setup/` · `auth/mfa/confirm/` | signed in | Start TOTP enrolment (returns a QR code) · confirm it with the first code |
| POST | `auth/password/` | signed in, `LOCAL` accounts | Change my password (`{old_password, new_password}`) |
| GET | `access-groups/mine/` | signed in | Groups I belong to, which I may assign on upload |

### 2.2 Administration (`accounts`, `evaluation`)

All of these also require an MFA-verified session.

| Method | Path | Permission | Does |
|---|---|---|---|
| GET · POST | `admin/users/` | `accounts.manage` | List (filter by role, group, active, locked) · create a user |
| GET · PATCH | `admin/users/{id}/` | `accounts.manage` | View · edit name, email, active flag |
| PUT | `admin/users/{id}/roles/` | `accounts.manage` | Replace roles. Refused if it would leave no active Admin |
| PUT | `admin/users/{id}/access-groups/` | `accounts.manage` | Replace group memberships; emits nothing, because search reads groups live |
| POST | `admin/users/{id}/unlock/` | `accounts.manage` | Clear the lockout |
| POST | `admin/users/{id}/reset-mfa/` | `accounts.manage` | Remove the user's TOTP device |
| GET | `admin/roles/` | `accounts.manage` | Roles with their permissions (read-only: roles are seeded) |
| GET · POST | `admin/access-groups/` | `accounts.manage` | List · create a group |
| PATCH · DELETE | `admin/access-groups/{id}/` | `accounts.manage` | Rename · delete (only when no document uses it) |
| GET | `admin/sessions/` | `accounts.manage` | Active sessions of all users |
| POST | `admin/sessions/{id}/revoke/` | `accounts.manage` | Revoke one session |
| GET | `audit-events/` | `audit.read` | Audit log; filter by actor, event type, entity, date range |

### 2.3 Pipeline configuration (`registry`)

| Method | Path | Permission | Does |
|---|---|---|---|
| GET | `pipelines/` | `pipelines.view` | Pipelines with their versions |
| GET | `pipeline-versions/{id}/` | `pipelines.view` | A version with steps, retrieval and generation settings |
| PATCH | `pipeline-versions/{id}/` | `pipelines.edit` | Edit a **draft**; a published version gives `409 version_published` |
| POST | `pipeline-versions/{id}/clone/` | `pipelines.edit` | New draft copied from this version; `created_by` = me |
| PUT | `pipeline-versions/{id}/steps/` | `pipelines.edit` | Replace the ordered steps of a draft (configs validated) |
| GET | `components/` · `models/` | `pipelines.view` | The component allow-list (with config schemas) · local models |
| GET · POST · PATCH | `retrieval-definitions/` · `generation-definitions/` | view: `pipelines.view` · change: `pipelines.edit` | Settings records. Records used by a published version cannot be changed; clone them instead |
| POST | `pipeline-versions/{id}/publish-initial/` | `releases.approve` | Publish the **first** version and its validated index generation, only when no published version exists yet |

### 2.4 Documents (`documents`)

| Method | Path | Permission | Does |
|---|---|---|---|
| GET | `documents/` | `documents.view` | Documents in my access groups; filter by status, type, group, filename |
| POST | `documents/` | `documents.upload` | Multipart `file` + `access_group_ids[]` → `201` with the document and its job, or `200` with `duplicate: true` and the existing document |
| GET | `documents/{id}/` | `documents.view` | Detail: versions, statuses, access groups, latest job |
| POST | `documents/{id}/versions/` | `documents.manage` | Upload a new version of the document |
| DELETE | `documents/{id}/` | `documents.manage` | Soft delete; removes it from both indexes |
| PUT | `documents/{id}/access/` | `documents.manage_access` | Replace the access groups (I must be in each group, Admins excepted); emits `index.acl` |
| GET | `documents/{id}/download/` | `documents.view` | Streams the original file (current version, or `?version=n`) |

### 2.5 Processing jobs (`processing`)

| Method | Path | Permission | Does |
|---|---|---|---|
| GET | `jobs/` | `jobs.view` | Jobs; filter by `document`, `status` |
| GET | `jobs/{id}/` | `jobs.view` | A job with its step runs, durations and errors |
| POST | `jobs/{id}/retry/` | `jobs.retry` | Re-queue a `FAILED` job; finished steps are skipped |
| POST | `jobs/{id}/cancel/` | `jobs.retry` | Cancel a `QUEUED` or `RUNNING` job |

### 2.6 Indexes (`indexing`)

| Method | Path | Permission | Does |
|---|---|---|---|
| GET | `index-generations/` | `indexes.view` | Generations with status, counts and the live one marked |
| POST | `index-generations/` | `indexes.build` | `{pipeline_version_id}` → new generation and a full build job |
| GET | `index-generations/{id}/` | `indexes.view` | Detail with build jobs and validation results |
| POST | `index-generations/{id}/validate/` | `indexes.build` | Run the validations again |
| POST | `index-generations/{id}/publish/` | `releases.approve` | Make the **first** validated generation live (later generations are released through `eval/runs/{id}/approve/`) |
| POST | `index-generations/{id}/rollback/` | `releases.approve` | Make this **retired** generation live again; it must still have its physical indexes |

Publishing a new generation happens through release approval ([2.8](#28-evaluation-and-release-evaluation)), together with its pipeline version.

### 2.7 Questions and answers (`retrieval`)

| Method | Path | Permission | Does |
|---|---|---|---|
| POST | `ask/` | `rag.ask` | `{question}` → event stream (below) |
| GET | `runs/` | `rag.ask` | My questions (`?mine=1`); users with `evaluation.view` may see everyone's |
| GET | `runs/{id}/` | `rag.ask` (own run) · `evaluation.view` (any run) | Question, validated answer, citations, status, latencies |
| GET | `chunks/{id}/` | `documents.view` | Chunk text, document, page and section, for the citation viewer; `404` outside my access groups |
| POST | `answers/{id}/feedback/` | `feedback.create` | `{rating: 1–5, text?}`; one per user per answer (a second post updates it) |
| GET | `failure-cases/` | `failures.review` | Failure cases; filter by type, review status |
| PATCH | `failure-cases/{id}/` | `failures.review` | Set `review_status`, `root_cause`, `resolution_notes` |

**`POST /ask/` stream.** Each event is a line `event: <name>` followed by a line `data: <json>`:

| Event | `data` | When |
|---|---|---|
| `meta` | `{run_id, request_id}` | first |
| `status` | `{stage: "queued" \| "searching" \| "reranking" \| "writing" \| "checking"}` | as each stage starts (`queued` while another answer is being written) |
| `token` | `{text}` | while the model writes the **draft** |
| `done` | `{answer_id, answer, citations: [{n, chunk_id, document_id, filename, page_start, page_end}], status: "VALIDATED" \| "REPAIRED"}` | after validation passes: the final answer |
| `abstain` | `{message, clarifying_question?}` | no good evidence, or validation failed after one repair |
| `error` | `{code, message}` | timeout, model or service failure |

The stream always ends with exactly one `done`, `abstain` or `error` event. A draft is never final until `done` arrives.

### 2.8 Evaluation and release (`evaluation`)

| Method | Path | Permission | Does |
|---|---|---|---|
| GET · POST | `eval/datasets/` | view: `evaluation.view` · create: `evaluation.manage_datasets` | Datasets and versions |
| GET · POST | `eval/datasets/{id}/cases/` | as above | Cases; adding cases to a frozen version gives `409`, so create a new version |
| POST | `eval/datasets/{id}/import/` | `evaluation.manage_datasets` | CSV or JSON file of cases |
| POST | `eval/datasets/{id}/cases/from-failures/` | `evaluation.manage_datasets` | Copy reviewed failure cases into a new dataset version |
| GET · POST | `eval/runs/` | view: `evaluation.view` · start: `evaluation.run` | Runs · start `{dataset_id, pipeline_version_id, index_generation_id}` |
| GET | `eval/runs/{id}/` | `evaluation.view` | Metric summary vs baseline, gate result, per-case results |
| GET | `eval/candidates/` | `evaluation.run` | What a run can measure: every live, building or validating generation with its pipeline version |
| POST | `eval/datasets/{id}/new-version/` | `evaluation.manage_datasets` | Copy a (frozen) dataset version into a new, editable version |
| PATCH · DELETE | `eval/cases/{id}/` | `evaluation.manage_datasets` | Edit or delete one case (not in a frozen version) |
| POST | `eval/runs/{id}/approve/` | `releases.approve` | Approve and publish (one transaction). Needs: run `PASSED`, approver ≠ the version's `created_by`, generation validated. Otherwise `409` explains which rule failed |

### 2.9 System (`core`)

| Method | Path | Permission | Does |
|---|---|---|---|
| GET | `health/` | none | `{status, services: {postgres, redis, minio, qdrant, opensearch, ollama}}`; `503` if any service is down. Returns no details beyond up or down |
| GET | `/api/schema/` · `/api/docs/` | signed in (`DEBUG`), `accounts.manage` otherwise | OpenAPI schema · Swagger UI |
