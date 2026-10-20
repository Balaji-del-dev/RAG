# 01 · Backend — Django project and apps

The backend is one Django 5.2 (LTS) project in `backend/`. It does two jobs:

- it serves the REST API (Django REST Framework) and the streamed chat answers;
- it holds the Celery tasks that process documents, build indexes and run evaluations.

Python 3.12. The packages are in [requirements.txt](../../requirements.txt).

## 1. Folder structure

```
backend/
├── manage.py
├── pyproject.toml              # ruff, mypy (django-stubs), pytest settings
├── .env.example                # every setting, with safe example values (the real .env is never committed)
├── config/                     # the Django project package
│   ├── __init__.py             # imports the Celery app so tasks register
│   ├── settings/
│   │   ├── base.py             # shared settings, read from environment variables
│   │   ├── local.py            # this machine: DEBUG on, Vite dev origin trusted
│   │   └── test.py             # test database, fast password hasher, eager outbox
│   ├── urls.py                 # /api/v1/… (one include per app), /api/schema/, /api/docs/
│   ├── asgi.py                 # uvicorn entry point (needed for streamed answers)
│   ├── wsgi.py
│   └── celery.py               # Celery app, queues, task defaults
├── apps/
│   ├── core/                   # shared base models, outbox, audit helper, service clients, health
│   ├── accounts/               # 4.7 users, sessions, roles, permissions, access groups
│   ├── registry/               # 4.1 pipelines, components, models, retrieval + generation settings
│   ├── documents/              # 4.2 documents, versions, metadata, artifacts, MinIO references
│   ├── processing/             # 4.3 jobs, step runs, elements, chunks, embeddings + the pipeline steps
│   ├── indexing/               # 4.4 index generations, builds, memberships, validations
│   ├── retrieval/              # 4.5 query orchestrator, runs, results, answers, feedback, failures
│   └── evaluation/             # 4.6 datasets, cases, runs, results, audit events
└── tests/
    ├── fixtures/               # one small sample file per supported format
    └── integration/            # tests that need the real local services (pytest -m integration)
```

### Inside each app

Every app uses the same layout, so finding code is predictable:

```
apps/<app>/
├── apps.py          # AppConfig: name = "apps.<app>", label = "<app>"
├── models.py        # tables for this app (db_table names match the schema diagram)
├── services.py      # business logic: every write goes through a service function
├── selectors.py     # read queries that apply the user's access scope
├── serializers.py   # DRF request/response shapes
├── views.py         # thin DRF views: check permission → call service/selector → serialize
├── urls.py
├── permissions.py   # DRF permission classes for this app's endpoints (only where needed)
├── tasks.py         # Celery tasks (thin: load IDs, call a service)
├── admin.py         # Django admin, for emergency use by Admins only
├── migrations/
└── tests/
```

**Code rules:**
1. Views stay thin. Business rules live in `services.py`, so the API, Celery tasks and management commands share them.
2. A function that changes state also writes its `outbox_events` row and its `audit_events` row, in the same database transaction.
3. Tasks receive IDs only, never model objects or file contents. They must be safe to run twice (idempotent).
4. An app may import from the apps listed **before** it in section 2, never from those after it. Two references point the other way, and both use Django string references (`"documents.Document"`), never imports:
   - `accounts.DocumentAccessGrant` → `documents.Document`;
   - the audit helper in `core` → `evaluation.AuditEvent`.
5. Pipeline components are loaded only from an **allow-list** in code (`implementation_key` → class). A class path is never read from the database or from a request.

## 2. The 8 apps

Listed in build and dependency order.

| # | App | Schema group | Tables it owns | What it does |
|---|---|---|---|---|
| 1 | `core` | — | `outbox_events` | Base model classes (UUID primary key, timestamps); outbox dispatcher; audit helper; clients for MinIO, Qdrant, OpenSearch, LiteLLM and the local models; health check; error format; request IDs; JSON logging |
| 2 | `accounts` | 4.7 Identity & access | `users`, `user_sessions`, `roles`, `permissions`, `role_permissions`, `user_roles`, `access_groups`, `user_access_groups`, `document_access_grants` | Sign-in, sign-out, MFA, lockout, sessions, roles and permissions, access groups, "access scope" for search, user administration |
| 3 | `registry` | 4.1 Pipeline configuration | `pipeline_definitions`, `pipeline_versions`, `pipeline_steps`, `component_definitions`, `model_definitions`, `retrieval_definitions`, `generation_definitions` | Draft and published pipeline versions, the component allow-list, model and setting records |
| 4 | `documents` | 4.2 Documents & MinIO | `documents`, `document_versions`, `document_metadata`, `extracted_artifacts`, `storage_objects` | Upload validation, storing originals in MinIO, versions, delete, download, changing access groups |
| 5 | `processing` | 4.3 Processing & chunks | `processing_jobs`, `processing_step_runs`, `document_elements`, `chunks`, `chunk_relationships`, `embedding_records` | The ingestion pipeline: read → parse → OCR → clean → structure → chunk → check → save → embed |
| 6 | `indexing` | 4.4 Index lifecycle | `index_generations`, `index_build_jobs`, `index_memberships`, `index_validations` | Build, update, validate, publish, roll back and reconcile the Qdrant and OpenSearch indexes |
| 7 | `retrieval` | 4.5 Retrieval & answers | `retrieval_runs`, `retrieval_results`, `answer_records`, `user_feedback`, `failure_cases` | The query orchestrator (question → grounded, cited answer), the citation viewer, feedback |
| 8 | `evaluation` | 4.6 Evaluation & audit | `evaluation_datasets`, `evaluation_cases`, `evaluation_runs`, `evaluation_results`, `audit_events` | Golden datasets, DeepEval runs, baseline comparison, failure review, release approval, the audit log |

Total: 1 + 9 + 7 + 5 + 6 + 4 + 5 + 5 = **42 tables**. Column-level detail is in [03-database.md](03-database.md) and the [schema diagram](../images/03-database-schema.png).

### 2.1 `core`

- **Base models:**
  - `UUIDModel`: `id = UUIDField(primary_key=True, default=uuid4)`.
  - `TimeStampedModel`: `created_at` and `updated_at`.
- **Outbox:**
  - The `OutboxEvent` model and `core.outbox.emit(event_type, aggregate, payload)`, called inside the caller's transaction.
  - The `run_outbox` management command is a long-running loop. It claims due rows with `SELECT … FOR UPDATE SKIP LOCKED LIMIT 200`, sends each one as a Celery task, and marks it `DISPATCHED`. On failure it increments `attempts` and moves `available_at` later (backoff).
  - Event types: `job.dispatch`, `index.upsert`, `index.delete`, `index.acl`.
- **Audit:** `core.audit.record(actor, event_type, entity, details, request)` writes `evaluation.AuditEvent`, including the actor's user ID and IP address.
- **Clients** (`core/clients/`), one small wrapper per service, so the rest of the code never imports a vendor SDK directly:

  | Module | Wraps | Used by |
  |---|---|---|
  | `storage.py` | MinIO through the S3 API (`minio` package) | documents, processing, evaluation |
  | `vector_store.py` | Qdrant (`qdrant-client`) | indexing, retrieval |
  | `search_index.py` | OpenSearch (`opensearch-py`) | indexing, retrieval |
  | `llm.py` | LiteLLM → Ollama at `127.0.0.1:11434`: timeouts, retries, streaming | retrieval, evaluation |
  | `embedder.py` | sentence-transformers, `multilingual-e5-small`, loaded once per process; adds the `query: ` / `passage: ` prefixes | processing, retrieval |
  | `reranker.py` | cross-encoder `ms-marco-MiniLM-L6-v2`, loaded once per process | retrieval |

- **Health:** `GET /api/v1/health/` checks PostgreSQL, Redis, MinIO, Qdrant, OpenSearch and Ollama. It returns `200` when all are up and `503` with the failing names otherwise.
- **Cross-cutting:**
  - Request ID middleware (also used as the trace ID).
  - A DRF exception handler that returns one error format ([04-api.md](04-api.md)).
  - structlog JSON logs.

### 2.2 `accounts`

Authentication answers *who are you?*; authorization answers *what may you do?*.

**Authentication**
- **User model:** a custom user model, `AUTH_USER_MODEL = "accounts.User"` (table `users`, UUID primary key). It must exist **before the first `migrate`**, because Django cannot switch to a custom user model later without rebuilding the database. It extends `AbstractBaseUser` and `PermissionsMixin`; the mixin is only there so the Django admin site works.
- **Passwords:** `PASSWORD_HASHERS` starts with Argon2 (`argon2-cffi`).
  - Minimum length 12 plus Django's common-password check.
  - LDAP / Active Directory is optional: `django-auth-ldap`, with `auth_source = LDAP` and no local password.
- **Sign-in:** `POST /api/v1/auth/login/`.
  - Django's `login()` rotates the session key.
  - A failure returns the same message whether the username exists or not.
- **Lockout:** `django-axes` locks the username for 15 minutes after 5 failures.
  - An axes signal copies the state to `users.failed_login_count` and `users.locked_until`, so the admin screen can show and clear it.
- **MFA:** TOTP through `django-otp`. It is required for the Admin role and optional for everyone else.
  - Sign-in answers `mfa_required: true`; the session counts as verified only after `POST /auth/mfa/verify/`.
  - Admin endpoints also require `request.user.is_verified()`.
- **Sessions:** Django's database session store, plus one `user_sessions` row per sign-in (SHA-256 of the session key, IP address, user agent).
  - `SessionGuardMiddleware` rejects revoked or expired sessions.
  - **Idle timeout:** 30 minutes. **Absolute timeout:** 8 hours.
  - `last_seen_at` is updated at most once a minute.
  - Revoking a session deletes the Django session and sets `revoked_at`.
- **Cookies:**
  - Session cookie: `HttpOnly`, `Secure`, `SameSite=Lax`. Browsers accept `Secure` cookies on `http://localhost`.
  - CSRF cookie: readable by the console (`CSRF_COOKIE_HTTPONLY = False`). Every POST, PUT, PATCH and DELETE must send `X-CSRFToken`.

**Authorization**
- **Roles and permissions:** stored in the schema's own tables (`roles`, `permissions`, `role_permissions`, `user_roles`).
  - `apps.accounts.backends.RoleBackend` answers `user.has_perm("rag.ask")` from the user's roles, cached once per request.
  - Django's built-in group and permission tables stay unused.
  - The superuser flag is for break-glass use only.
- **DRF:**
  - The default permission is `IsAuthenticated`.
  - Each view adds `HasPerm("…")`. Every endpoint has a test that it returns 403 without the permission.
- **Access scope:** `accounts.selectors.access_scope(user) -> frozenset[str]` returns the names of the user's access groups. It is read from PostgreSQL for the signed-in user, **never taken from the request**. Retrieval, downloads, citations and document lists all use it.
- **Seed data:** a data migration creates the six roles, their permissions and the `general` access group ([03-database.md](03-database.md#8-seed-data)).

| Role | Permissions |
|---|---|
| User (every account) | `rag.ask` · `documents.view` · `feedback.create` |
| Knowledge manager | `documents.upload` · `documents.manage` (new version, delete) · `documents.manage_access` · `jobs.view` · `jobs.retry` |
| Pipeline engineer | `pipelines.view` · `pipelines.edit` · `indexes.view` · `indexes.build` · `jobs.view` · `jobs.retry` |
| Evaluator | `evaluation.view` · `evaluation.manage_datasets` · `evaluation.run` · `failures.review` · `pipelines.view` |
| Release approver | `releases.approve` · `evaluation.view` · `pipelines.view` · `indexes.view` |
| Admin | `accounts.manage` (users, roles, access groups, sessions, unlock) · `audit.read` |

A person can hold several roles; their permissions add up.

**Two safety rules in code:**
- the last active Admin cannot be removed or deactivated;
- a Release approver can never approve a pipeline version they created (`pipeline_versions.created_by`).

### 2.3 `registry`

- **Versions:**
  - A pipeline has numbered versions: `DRAFT → PUBLISHED → RETIRED`.
  - Only drafts can be edited. Editing a published version returns `409`; to change it, clone it into a new draft.
  - `created_by` is set when the draft is created.
- **Components:**
  - Each component class declares a pydantic config model. `component_definitions.config_schema` stores that model's JSON schema.
  - Step configs are validated by the pydantic model when they are saved.
- **Baseline components** (the allow-list, `implementation_key` → class):

  | Stage | Keys |
  |---|---|
  | Read & extract | `read.minio_original`, `parse.docling`, `parse.pymupdf`, `parse.plain` (TXT, MD, CSV, JSON, XML), `ocr.tesseract`, `ocr.easyocr` |
  | Clean & structure | `clean.normalize`, `structure.rebuild`, `enrich.none` (placeholder for optional labels) |
  | Chunk | `chunk.structure_aware`, `chunk.quality_checks`, `chunk.persist` |
  | Embed | `embed.sentence_transformers` |
  | Retrieve & answer | `retrieve.qdrant_dense`, `retrieve.opensearch_bm25`, `fuse.rrf`, `rerank.cross_encoder`, `context.budget`, `generate.litellm`, `validate.citations` |

- **Publishing:** a version becomes `PUBLISHED` only through release approval ([2.8](#28-evaluation)). The one exception is the very first version, which a Release approver may publish with no evaluation run, because no baseline exists yet.

### 2.4 `documents`

- **Upload:** `POST /api/v1/documents/` (multipart). Checks run in this order, and the first failure stops the upload:
  1. **Permission and groups:** the user has `documents.upload`, and every chosen access group is one they belong to (Admins may choose any group). At least one group is required.
  2. **Extension** is one of the first-release formats: PDF, DOCX, XLSX, PPTX, TXT, MD, CSV, JSON, XML, HTML.
  3. **MIME type** sniffed from the content (`python-magic`) matches the extension. The browser's content type is ignored.
  4. **Size** ≤ `UPLOAD_MAX_BYTES` (50 MB by default).
  5. **Content:**
     - Office files (zip-based): limits on uncompressed size and entry count, to stop zip bombs.
     - PDFs: must open; encrypted PDFs are rejected; page limit.
  6. **Duplicate:** SHA-256 of the bytes. If a live document already has the same bytes, the existing document and its status are returned with `duplicate: true`.
- **Storage:**
  - The object key is generated by the server: `rag-originals/documents/<document_id>/v<n>/<sha256>.<ext>`.
  - The object is stored **first**. Then **one transaction** writes the `documents` and `document_versions` rows, the `document_access_grants`, a `processing_jobs` row and the `job.dispatch` outbox row.
  - A nightly job removes objects that have no row and are older than one day.
- **New version:**
  - `POST /documents/{id}/versions/` adds a version.
  - The previous version becomes `SUPERSEDED` when the new one is `PUBLISHED`.
- **Delete:** a soft delete.
  - Sets `deleted_at` and the status `DELETED`.
  - Emits `index.delete`.
  - MinIO bytes are removed only after the lifecycle checks pass, i.e. no retained version or published generation still references them.
- **Access change:** `PUT /documents/{id}/access/` replaces the grants and emits `index.acl`.
- **Download and citations:**
  - The file is streamed through Django after an access-scope check.
  - A document outside the user's scope returns `404`, not `403`, so its existence is not revealed.

### 2.5 `processing`

- **The task:** `processing.tasks.run_job(job_id)` runs the enabled steps of the job's pipeline version, in `step_order`.
  - Each step writes a `processing_step_runs` row with its status, input and output summaries, duration and error.
  - On retry, steps that already succeeded are skipped.
- **Errors:** a transient error (a connection or timeout) is retried with backoff, up to 3 times. A content error (an unreadable file) fails at once and keeps its message.
- **The steps** (they match diagram 01, stages 1–4):

  | # | Step | Detail |
  |---|---|---|
  | 1 | Read original | Read from MinIO; re-check the SHA-256 |
  | 2 | Parse | Docling (PDF, DOCX, PPTX, XLSX, HTML, MD) and PyMuPDF (PDF text and pages); simple readers for TXT, CSV, JSON and XML. The Docling JSON is saved to `rag-artifacts` and recorded in `extracted_artifacts` |
  | 3 | OCR fallback | Only for pages with too little text (for example under 50 characters): Tesseract with `eng+tam+hin`. EasyOCR (`gpu=False`) only when Tesseract's confidence is low |
  | 4 | Normalize | Unicode NFKC, whitespace, line-break hyphenation |
  | 5 | Rebuild structure | `document_elements`: headings, sections, tables, page map, `section_path` |
  | 6 | Enrich | Off in the baseline (`enrich.none`) |
  | 7 | Chunk | Structure-aware, at most ~400 tokens (the e5 model's limit is 512, including the prefix), ~50 tokens of overlap. Tables stay whole or are split by rows with the header repeated. Parent–child links go in `chunk_relationships` |
  | 8 | Quality checks | Drop or flag empty, oversized, duplicate (`content_hash`) and broken-table chunks |
  | 9 | Save chunks | One transaction; chunk ID = `uuid5(namespace, document_version_id · pipeline_version_id · chunk_index · content_hash)` |
  | 10 | Embed | Batches of 16–32 on the CPU; `passage: ` prefix; normalized vectors; `embedding_records`. The final transaction also writes the `index.upsert` outbox row |

- **Memory on this machine:**
  - The worker runs with `--max-tasks-per-child=20` to free memory.
  - Large PDFs are parsed in page batches.
  - Time limits: soft 30 minutes, hard 35 minutes.

### 2.6 `indexing`

- **Names:** one **index generation** per pipeline version, named `rag_chunks_g<NNNN>` in Qdrant and `rag_chunks_v<NNN>` in OpenSearch. The names are recorded in `index_generations`.
- **Tasks:**

  | Task | Started by | Does |
  |---|---|---|
  | `upsert_version(document_version_id)` | outbox `index.upsert` | Upsert the version's chunks into every live generation of its pipeline version, in both engines, keyed by chunk ID, with `access_groups`. Marks `index_memberships` `INDEXED`; when both engines confirm, the document version becomes `PUBLISHED` |
  | `delete_version(document_version_id)` | outbox `index.delete` | Delete by `document_version_id` filter in both engines; memberships → `REMOVED` |
  | `update_acl(document_id)` | outbox `index.acl` | Rewrite `access_groups`: Qdrant `set_payload` by filter, OpenSearch `update_by_query`, in every non-retired generation |
  | `build_generation(generation_id)` | `index_build_jobs` (API) | Full build of a new generation from the canonical chunks in PostgreSQL; OpenSearch `refresh_interval: -1` while building |
  | `validate_generation(generation_id)` | after a build | Counts, missing, duplicate and orphaned records, dense, lexical and hybrid smoke searches → `index_validations` |
  | `reconcile()` | Celery beat, nightly | Compare `index_memberships` with both engines; repair drift; report what changed |

- **Publish and rollback:** both happen in **one PostgreSQL transaction**, and only when both indexes pass validation.
  - Publish: the new generation becomes `PUBLISHED` and the old one `RETIRED`.
  - The retired generation is kept for rollback until nothing references it.
  - Rollback re-publishes the previous generation.

### 2.7 `retrieval`

**The query orchestrator** follows diagram 05.

**Async view.** `POST /api/v1/ask/` is a plain Django **async** view, because DRF views are synchronous.
- Under ASGI, Django runs synchronous views one at a time in a single thread. A 20–60 second answer would block every other request.
- The LLM call uses LiteLLM's async streaming.
- CPU-heavy work (embedding the query, reranking) runs in a worker thread (`asyncio.to_thread`).

**The steps:**
1. **Authenticate and authorize:** a valid session, `rag.ask`, and the per-user rate limit (10 questions per minute). The question must be at most 2,000 characters. A `request_id` and `trace_id` are assigned.
2. **Resolve the access scope:** the user's access groups (section 2.2).
3. **Plan:**
   - Normalize and classify the question.
   - Load the published pipeline version and index generation, with their physical names, from PostgreSQL.
   - Load the settings from `retrieval_definitions` and `generation_definitions`.
4. **Retrieve:** Qdrant dense (top 20) and OpenSearch BM25 (top 20) run **in parallel**.
   - Both use the same mandatory filter: `index_generation_id` plus `access_groups ∈ scope`.
   - Results go to `retrieval_results`.
5. **Fuse:** normalize, dedupe by chunk, RRF with k = 60.
6. **Rerank:** the cross-encoder scores the top 15. MMR and parent expansion are off in the baseline.
7. **Build context:** the best 3–4 chunks, within about 1,500 tokens.
   - If the best rerank score is under the threshold, the answer is an **abstention** ("I could not find this in the documents you can access").
8. **Generate:** a grounded prompt goes to LiteLLM → Ollama `qwen2.5:3b` (temperature 0.1, at most 400 output tokens, 120-second timeout).
   - Chunks are passed as quoted data with their IDs.
   - The prompt tells the model to ignore any instructions inside the chunks.
9. **Validate:**
   - The answer schema is correct.
   - Every citation refers to a chunk that was actually given to the model.
   - There is at least one citation unless the answer abstains.
   - If validation fails, **repair once** (one re-prompt) or abstain.
10. **Save:** `retrieval_runs`, `retrieval_results` and `answer_records`, then send the final event.

**Streaming decision:**
- Tokens are streamed to the console as a **draft**, shown as "checking sources…".
- The answer becomes final, with clickable citations, only on the `done` event after validation.
- If validation fails, the console replaces the draft with the abstention.
- Only validated answers are ever stored or returned by `GET /runs/{id}/`.

**Answer cache** (off by default; turn it on only when the numbers justify it):
- keyed by normalized question, generation ID and a hash of the access scope;
- Redis database 1, 1-hour time to live.

**Feedback:**
- `POST /answers/{id}/feedback/` writes `user_feedback`.
- A rating of 1–2 out of 5 also opens a `failure_cases` row for review.

**Citation viewer:** `GET /chunks/{id}/` returns the chunk text, document, page and section, after the access-scope check.

### 2.8 `evaluation`

- **Datasets:**
  - Datasets are versioned. A dataset version is frozen once a run has used it.
  - Cases are added by hand, imported from CSV or JSON, or created from reviewed `failure_cases`.
- **Runs:**
  - `evaluation.tasks.run_evaluation(run_id)` runs on the `evaluation` queue as the **evaluation service account** (`svc-evaluation`). That account has no password and cannot sign in, and it is in every access group.
  - For each case it runs the orchestrator (not streamed) on the *candidate* pipeline version and generation.
- **Metrics:**
  - Retrieval metrics, computed in our own code from `expected_sources`: hit@k, recall@k and MRR.
  - Answer metrics from DeepEval: faithfulness, answer relevancy, contextual precision and contextual recall. The judge is the local `qwen2.5:3b` through Ollama.
- **On this CPU:**
  - Each case needs several LLM calls, so 30–50 cases can take a few hours. Run evaluations overnight and pause chat during them.
  - Keep the judge model fixed across the runs you compare. Calibrate it on 20–30 cases labelled by a person.
- **Gates:** `summary_json` stores each metric next to the baseline. A run **passes** when no metric is below its threshold and none falls more than the allowed drop below the baseline. Both numbers are kept in settings.
- **Approval:** `POST /eval/runs/{id}/approve/` requires all of these:
  - the caller has `releases.approve`;
  - the run passed its gates;
  - the caller is **not** the version's `created_by` (the four-eyes rule).

  One transaction then:
  - sets `evaluation_runs.approved_by`;
  - publishes the pipeline version (`published_by`, `published_at`) and its index generation;
  - writes an audit event.
- **Audit log:** `audit_events` lives in this app. Every app writes to it through `core.audit.record`; Admins read it at `GET /audit-events/`.

## 3. Settings — environment variables

Kept in `backend/.env`: file mode 600, listed in `.gitignore`, never committed. `.env.example` holds the same names with example values.

| Variable | Example | Notes |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.local` | |
| `SECRET_KEY` | (50+ random characters) | |
| `DEBUG` | `true` locally, `false` in daily use | |
| `ALLOWED_HOSTS` | `127.0.0.1,localhost` | |
| `CSRF_TRUSTED_ORIGINS` | `http://localhost:5173` | the Vite dev server (local settings only) |
| `DATABASE_URL` | `postgres://rag_app:…@127.0.0.1:5432/rag_platform` | |
| `CELERY_BROKER_URL` | `redis://:…@127.0.0.1:6379/0` | Redis database 0 = broker |
| `CACHE_URL` | `redis://:…@127.0.0.1:6379/1` | Redis database 1 = cache, throttles |
| `S3_ENDPOINT_URL` · `S3_ACCESS_KEY` · `S3_SECRET_KEY` | `http://127.0.0.1:9000` · … | the MinIO app user, not the root user |
| `S3_BUCKET_ORIGINALS` · `S3_BUCKET_ARTIFACTS` · `S3_BUCKET_EXPORTS` | `rag-originals` · `rag-artifacts` · `rag-exports` | |
| `QDRANT_URL` · `QDRANT_API_KEY` | `http://127.0.0.1:6333` · … | |
| `OPENSEARCH_URL` · `OPENSEARCH_USER` · `OPENSEARCH_PASSWORD` · `OPENSEARCH_CA_CERT` | `https://127.0.0.1:9200` · `rag_app` · … | its own service user, not `admin` |
| `LLM_MODEL` · `LLM_FALLBACK_MODEL` · `OLLAMA_API_BASE` | `ollama/qwen2.5:3b` · `ollama/qwen2.5:1.5b` · `http://127.0.0.1:11434` | |
| `EMBEDDING_MODEL_DIR` · `RERANKER_MODEL_DIR` | `~/rag-data/models/multilingual-e5-small` · `…/ms-marco-MiniLM-L6-v2` | local folders, never a download |
| `HF_HUB_OFFLINE` · `TRANSFORMERS_OFFLINE` · `OMP_NUM_THREADS` | `1` · `1` · `4` | |
| `UPLOAD_MAX_BYTES` | `52428800` | 50 MB |
| `SESSION_IDLE_MINUTES` · `SESSION_MAX_HOURS` | `30` · `8` | |

## 4. Background work

**Celery settings:**
- JSON serializer only.
- `task_acks_late = True`, `worker_prefetch_multiplier = 1`.
- Retries with exponential backoff and jitter.
- Every task has a time limit.
- Task names are `<app>.<task>`.

| Queue | Tasks |
|---|---|
| `ingest` | `processing.run_job` |
| `index` | `indexing.upsert_version`, `indexing.delete_version`, `indexing.update_acl`, `indexing.build_generation`, `indexing.validate_generation` |
| `evaluation` | `evaluation.run_evaluation` |
| (Celery beat) | `accounts.purge_expired_sessions` (daily), `indexing.reconcile` (nightly), `documents.remove_orphan_objects` (nightly), `core.purge_dispatched_outbox` (daily, keeps 7 days) |

**Outbox event → task:**

| Event | Task |
|---|---|
| `job.dispatch` | `processing.run_job` |
| `index.upsert` | `indexing.upsert_version` |
| `index.delete` | `indexing.delete_version` |
| `index.acl` | `indexing.update_acl` |

## 5. Processes on this machine

All of them bind to `127.0.0.1`.

| Process | Command (from `backend/`) | Port | Memory (approx.) |
|---|---|---|---|
| API | `uvicorn config.asgi:application --host 127.0.0.1 --port 8000` | 8000 | ~0.9 GB (with the embedder and reranker) |
| Outbox dispatcher | `python manage.py run_outbox` | — | ~0.1 GB |
| Celery worker | `celery -A config worker -Q ingest,index,evaluation --concurrency=1 --max-tasks-per-child=20` | — | 1.5–2 GB while processing |
| Celery beat | `celery -A config beat` | — | small |
| Flower | `celery -A config flower --address=127.0.0.1 --port=5555` | 5555 | small |

The backing services (PostgreSQL, Redis, MinIO, Qdrant, OpenSearch, Ollama) are covered in [execution/phase-00-machine-setup.md](execution/phase-00-machine-setup.md).

**Memory rule:** while answering questions, stop the Celery worker; while ingesting, chat less (see [dependency.txt](../../dependency.txt)). Phase 9 adds start and stop scripts for both modes.

## 6. Quality: tests, linting, logs

- **Tests:** `pytest` + `pytest-django` + `factory-boy`.
  - Unit tests per app.
  - `tests/integration/` runs against the real local services and is marked `integration`.
  - Every endpoint has a test for 401 (not signed in), 403 (no permission) and the success case.
- **Lint and types:**
  - `ruff check` and `ruff format`.
  - `mypy` with `django-stubs` and `djangorestframework-stubs`.
  - All three must pass before a phase is done.
- **Logs:**
  - structlog JSON, one line per event, always with `request_id`, `user_id` and `trace_id`.
  - Logs never contain passwords, session keys, CSRF tokens or document text.
- **API schema:** drf-spectacular generates `/api/schema/`, which the console's types are checked against.
