# 03 · Database and storage

Data lives in five stores. Each one has one clear job:

| Store | Owns | Source of truth? | If it is lost |
|---|---|---|---|
| **PostgreSQL 16** | Configuration, documents and versions, canonical chunk text, jobs, index state, questions and answers, evaluation, audit, users, roles, access groups | **Yes**, for all metadata and lifecycle state | Restore from backup |
| **MinIO** (S3 API) | File bytes: originals, extracted artifacts, OCR output, evaluation exports | **Yes**, for file contents | Restore from backup |
| **Qdrant** | Dense vectors + small payload (IDs, pages, `access_groups`) | No (derived) | Rebuild from PostgreSQL chunks (re-embed) |
| **OpenSearch** | BM25 text index + keyword fields (IDs, `access_groups`) | No (derived) | Rebuild from PostgreSQL chunks |
| **Redis** | Celery messages, cache, rate-limit counters | No (transient) | Undelivered work is re-sent from `outbox_events` |

The diagrams show the same design:
- [Data & storage architecture](../images/02-database-architecture.png): what each store owns, how they stay in sync, the four paths;
- [PostgreSQL schema](../images/03-database-schema.png): every column, type and key.

## 1. PostgreSQL setup

| Item | Value |
|---|---|
| Database | `rag_platform` (tests use `test_rag_platform`, created by the test runner) |
| App role | `rag_app`: owns the schema; `LOGIN`, `CREATEDB` (for tests), **not** superuser |
| Address | `127.0.0.1:5432` only (`listen_addresses = 'localhost'`; `pg_hba.conf` uses `scram-sha-256`) |
| Time zone | UTC in the database (`USE_TZ = True`); the console shows local time |
| Driver | psycopg 3; `CONN_MAX_AGE = 60`; health checks on |
| Extensions | none needed (UUIDs are made in Python) |

## 2. Conventions

- **Keys:**
  - The primary key is a **UUID** (`uuid4`).
  - The exceptions are `outbox_events` and `audit_events`, which use `bigint` identity keys because rows are only ever appended.
  - Chunk IDs are **deterministic**: `uuid5(namespace, document_version_id · pipeline_version_id · chunk_index · content_hash)`. A retry therefore produces the same IDs.
- **Foreign keys:** every reference is a real foreign key with `on_delete=PROTECT`, except child rows that belong to their parent (for example `processing_step_runs`), which use `CASCADE`. Documents are soft-deleted (`deleted_at`), so their rows stay.
- **Time:** `timestamptz` everywhere.
- **Status columns:** Django `TextChoices` with a database `CHECK` constraint listing the allowed values.
- **JSONB** holds flexible detail only (configuration, citations, diagnostics), **never** IDs, scores or statuses. Every JSONB config is validated by a pydantic model before saving.
- **Schema changes:** only through Django migrations. Each migration is reviewed and committed with the code that needs it.
- **Table names:** `db_table` matches the names in the schema diagram (`users`, `chunks`, …), not Django's default `app_model` names.

## 3. Tables by app

42 tables. **ADDED** = not in the original brief (see [../README.md](../README.md#additions-to-the-briefs-schema)).

### `accounts`: 4.7 Identity & access (ADDED)

| Table | Holds | Keys and checks |
|---|---|---|
| `users` | One row per person or service account; Argon2 `password_hash` (empty for LDAP and service accounts); `auth_source`; lock state; `mfa_enabled` | `username` UQ, `email` UQ |
| `user_sessions` | One row per sign-in: SHA-256 of the session key, IP, user agent, `last_seen_at`, `expires_at`, `revoked_at` | `session_key_hash` UQ; index `(user_id, expires_at)` |
| `roles` | The six roles; `is_system` roles cannot be deleted | `name` UQ |
| `permissions` | Permission codenames such as `rag.ask` | `codename` UQ |
| `role_permissions` | Which permissions a role has | `(role_id, permission_id)` UQ |
| `user_roles` | Which roles a user holds; `granted_by`, `granted_at` | `(user_id, role_id)` UQ |
| `access_groups` | Groups that documents are shared with (for example `general`, `finance`, `hr`) | `name` UQ |
| `user_access_groups` | Which groups a user belongs to | `(user_id, access_group_id)` UQ |
| `document_access_grants` | Which groups may read a document; `access_level` | `(document_id, access_group_id)` UQ |

### `core`

| Table | Holds | Keys and checks |
|---|---|---|
| `outbox_events` (ADDED) | Events to send to Celery: `job.dispatch`, `index.upsert`, `index.delete`, `index.acl` | `bigint` PK; partial index `(available_at) WHERE status = 'PENDING'` |

### `registry`: 4.1 Pipeline configuration

| Table | Holds | Keys and checks |
|---|---|---|
| `pipeline_definitions` | A named pipeline (the first release has one: `default`) | `name` UQ; at most one row with `is_active = true` (partial UQ) |
| `pipeline_versions` | Numbered versions with `config_json`, links to retrieval and generation settings, `created_by` (author), `published_by`, `published_at` | `(pipeline_id, version_number)` UQ; at most one `PUBLISHED` version per pipeline (partial UQ) |
| `pipeline_steps` | Ordered steps of a version: component + config + enabled | `(pipeline_version_id, step_order)` UQ |
| `component_definitions` | The allow-list: `implementation_key` and the JSON schema of its config | `name` UQ |
| `model_definitions` | Local models: provider, model name, type, parameters | `name` UQ |
| `retrieval_definitions` | Dense, BM25, fusion, reranker and context settings | `name` UQ |
| `generation_definitions` | Model, prompt template, generation, citation and abstention settings | `name` UQ |

### `documents`: 4.2 Documents & MinIO

| Table | Holds | Keys and checks |
|---|---|---|
| `documents` | One logical document: filename, type, `current_version_id`, `lifecycle_status`, `created_by`, `deleted_at` | index `lifecycle_status` |
| `document_versions` | Each uploaded file: SHA-256, size, MinIO bucket + key + version ID, `status` | `(document_id, version_number)` UQ; index `content_sha256` |
| `document_metadata` | Metadata extracted for a version (title, author, language, …) | `document_version_id` UQ |
| `extracted_artifacts` | Artifacts in MinIO made from a version (Docling JSON, page text, OCR text) | index `document_version_id` |
| `storage_objects` (optional) | Shared registry of MinIO objects, so shared bytes are never deleted early | `(bucket, object_key, object_version_id)` UQ; index `content_sha256` |

### `processing`: 4.3 Processing & chunks

| Table | Holds | Keys and checks |
|---|---|---|
| `processing_jobs` | One ingest run of a version with a pipeline version: status, attempts, times, error | index `(status, created_at)`; index `document_version_id` |
| `processing_step_runs` | One row per step per job: status, input/output summaries, duration, error | index `processing_job_id` |
| `document_elements` | Structured pieces: heading, paragraph, table, … with page and `section_path` | index `(document_version_id, element_order)` |
| `chunks` | **Canonical chunk text**, token count, pages, section path, `content_hash`, parent link | `(document_version_id, pipeline_version_id, chunk_index)` UQ; index `parent_chunk_id`; `CHECK page_end >= page_start` |
| `chunk_relationships` | Links between chunks (next, parent, same table) | `(source_chunk_id, target_chunk_id, relationship_type)` UQ |
| `embedding_records` | Which model and revision embedded a chunk, vector size, Qdrant point ID | `(chunk_id, model_id, model_version)` UQ |

### `indexing`: 4.4 Index lifecycle

| Table | Holds | Keys and checks |
|---|---|---|
| `index_generations` | One coordinated pair: Qdrant collection + OpenSearch index names, status | `(pipeline_version_id, generation_number)` UQ; **at most one `PUBLISHED` row** (partial UQ) |
| `index_build_jobs` | Full builds of a generation | index `index_generation_id` |
| `index_memberships` | Every chunk in a generation, with its Qdrant point ID, OpenSearch `_id` and status | `(index_generation_id, chunk_id)` UQ; index `(index_generation_id, document_version_id)` |
| `index_validations` | Results of each check: counts, missing, duplicates, orphans, smoke searches | index `index_generation_id` |

### `retrieval`: 4.5 Retrieval, answers & feedback

| Table | Holds | Keys and checks |
|---|---|---|
| `retrieval_runs` | One question: who asked (`user_id`), text, pipeline version, generation, status, latency, `trace_id` | `request_id` UQ; index `(user_id, created_at)`; index `trace_id` |
| `retrieval_results` | Every candidate chunk: source (dense, lexical, both), original rank and score, fusion rank, rerank score | index `(retrieval_run_id, fusion_rank)` |
| `answer_records` | The validated answer, citations (JSONB), status, model, prompt version, latency, token use | index `retrieval_run_id` |
| `user_feedback` | Rating 1–5 and comment, by `user_id` | `CHECK rating BETWEEN 1 AND 5`; `(answer_id, user_id)` UQ |
| `failure_cases` | Problems to review: type, root cause, review status, resolution | index `review_status` |

### `evaluation`: 4.6 Evaluation & audit

| Table | Holds | Keys and checks |
|---|---|---|
| `evaluation_datasets` | Named, versioned golden sets | `(name, version)` UQ |
| `evaluation_cases` | Question, expected answer, expected sources, case type | index `dataset_id` |
| `evaluation_runs` | A run of a dataset on a pipeline version + generation: status, metric summary, `approved_by` | index `(pipeline_version_id, started_at)` |
| `evaluation_results` | One score per case per metric, passed or not | `(evaluation_run_id, evaluation_case_id, metric_name)` UQ |
| `audit_events` | Append-only log: who (`actor_user_id`, IP), what, which entity, details | `bigint` PK; index `created_at`; index `(entity_type, entity_id)` |

## 4. Status values

Each lifecycle is stored in PostgreSQL. The status columns drive the Celery workers, the console's status badges and the cleanup jobs.

| Column | Values (→ = normal order) |
|---|---|
| `document_versions.status` | `UPLOADED → VALIDATING → QUEUED → PROCESSING → INDEXING → VALIDATING_INDEX → PUBLISHED` · `FAILED` · `SUPERSEDED` · `DELETED` |
| `documents.lifecycle_status` | `PENDING → ACTIVE` (has a published version) · `FAILED` · `DELETED` |
| `pipeline_versions.status` | `DRAFT → PUBLISHED → RETIRED` |
| `processing_jobs.status` · `index_build_jobs.status` | `QUEUED → RUNNING → SUCCEEDED` · `FAILED → RETRY` · `CANCELLED` |
| `processing_step_runs.status` | `RUNNING → SUCCEEDED` · `FAILED` · `SKIPPED` |
| `embedding_records.status` | `PENDING → EMBEDDED` · `FAILED` |
| `index_generations.status` | `BUILDING → VALIDATING → PUBLISHED → RETIRED` · `FAILED` |
| `index_memberships.status` | `PENDING → INDEXED` · `FAILED → RETRY` · `REMOVED` |
| `index_validations.status` | `PASSED` · `FAILED` |
| `outbox_events.status` | `PENDING → DISPATCHED` · `FAILED → RETRY` |
| `retrieval_runs.status` | `RUNNING → ANSWERED` · `ABSTAINED` · `REJECTED` · `FAILED` |
| `answer_records.status` | `VALIDATED` · `REPAIRED` (passed after one repair) · `ABSTAINED` · `REJECTED` |
| `failure_cases.review_status` | `OPEN → IN_REVIEW → RESOLVED` · `WONT_FIX` |
| `evaluation_runs.status` | `QUEUED → RUNNING → PASSED` · `FAILED` (gates not met) · `ERROR` |
| `users` (from `is_active`, `locked_until`) · `user_sessions` | user `ACTIVE → LOCKED` (after failed sign-ins) `→ ACTIVE` · `DISABLED`; session `ACTIVE → EXPIRED` · `REVOKED` |

**Other enum columns:**

| Column | Values |
|---|---|
| `users.auth_source` | `LOCAL` · `LDAP` |
| `document_access_grants.access_level` | `READ` · `MANAGE` |
| `component_definitions.component_type` | `READER` · `PARSER` · `OCR` · `CLEANER` · `STRUCTURE` · `ENRICHER` · `CHUNKER` · `CHUNK_CHECK` · `PERSIST` · `EMBEDDER` · `RETRIEVER` · `FUSION` · `RERANKER` · `CONTEXT` · `GENERATOR` · `VALIDATOR` |
| `model_definitions.model_type` | `LLM` · `EMBEDDING` · `RERANKER` · `OCR` · `LAYOUT` |
| `extracted_artifacts.artifact_type` · `storage_objects.object_type` | `DOCLING_JSON` · `PAGE_TEXT` · `OCR_TEXT` · `TABLE` · `IMAGE` · `ORIGINAL` · `EXPORT` |
| `processing_jobs.job_type` | `INGEST` · `REPROCESS` |
| `document_elements.element_type` | `TITLE` · `HEADING` · `PARAGRAPH` · `LIST_ITEM` · `TABLE` · `CAPTION` · `CODE` · `FOOTNOTE` · `PAGE_HEADER` · `PAGE_FOOTER` |
| `chunk_relationships.relationship_type` | `NEXT` · `PARENT` · `SAME_TABLE` |
| `index_validations.validation_type` | `COUNT` · `MISSING` · `DUPLICATE` · `ORPHAN` · `SMOKE_DENSE` · `SMOKE_LEXICAL` · `SMOKE_HYBRID` |
| `retrieval_results.retrieval_source` | `DENSE` · `LEXICAL` · `BOTH` |
| `failure_cases.failure_type` | `NO_RETRIEVAL` · `WRONG_RETRIEVAL` · `NOT_GROUNDED` · `WRONG_CITATION` · `INCOMPLETE` · `FORMAT` · `SAFETY` · `LATENCY` |
| `evaluation_cases.case_type` | `FACTUAL` · `MULTI_HOP` · `TABLE` · `NO_ANSWER` (must abstain) · `ACCESS` (must not see) · `MULTILINGUAL` |

## 5. Framework tables (not in the 42)

Django and its add-ons create their own tables:
- Django: `django_migrations`, `django_content_type`, `django_session`, `django_admin_log`, `auth_group`, `auth_permission`, `auth_group_permissions`;
- the user model's mixin: `users_groups`, `users_user_permissions`;
- django-axes: `axes_accessattempt`, `axes_accesslog`, `axes_accessfailurelog`;
- django-otp: `otp_totp_totpdevice`.

We do not draw them. Django's group and permission tables stay empty, because roles live in our own tables.

## 6. Migration order

Migrations are added phase by phase. Django resolves the dependencies, but the **very first** migration must contain the custom user model:

| # | Migration | Phase | Contains | Why here |
|---|---|---|---|---|
| 1 | `accounts 0001` | 1 | `users` | `AUTH_USER_MODEL` must exist before anything else |
| 2 | `core 0001` | 1 | `outbox_events` | |
| 3 | `evaluation 0001` | 1 | `audit_events` | every later phase writes audit events |
| 4 | `accounts 0002` | 2 | `user_sessions`, `roles`, `permissions`, `role_permissions`, `user_roles`, `access_groups`, `user_access_groups` | |
| 5 | `accounts 0003` (data) | 2 | 6 roles, 19 permissions, role–permission pairs, `general` group | seed data, section 8 |
| 6 | `registry 0001` + `0002` (data) | 3 | the 7 tables of 4.1 + components, models, baseline settings, default pipeline v1 | references `users` (`created_by`, `published_by`) |
| 7 | `documents 0001` | 4 | the 5 tables of 4.2 | references `users`, `registry` |
| 8 | `accounts 0004` | 4 | `document_access_grants` | references `documents` |
| 9 | `processing 0001` | 5 | the 6 tables of 4.3 | references documents, registry |
| 10 | `indexing 0001` | 6 | the 4 tables of 4.4 | references processing, registry |
| 11 | `retrieval 0001` | 7 | the 5 tables of 4.5 | references indexing, processing, users |
| 12 | `evaluation 0002` + `0003` (data) | 8 | datasets, cases, runs, results + the `svc-evaluation` account | references retrieval, indexing, registry |

**Status (2026-10-20):** migrations 1–4 and 7–11 are applied, plus `evaluation 0002`. All 42 tables exist; `accounts 0005` also made four description and user-agent columns nullable to match the diagram. The seed data of `registry 0002` and `evaluation 0003` still comes in Phases 3 and 8. A test (`backend/tests/test_schema_matches_diagram.py`) checks every table, column and nullability against `docs/src/build_schema.py`.

## 7. Important rules the database enforces

- **One live generation:** a partial unique index allows only one `index_generations` row with `status = 'PUBLISHED'`. Publishing is one transaction: the old row becomes `RETIRED` and the new one `PUBLISHED`.
- **Published versions do not change:** the service layer refuses edits to a `PUBLISHED` pipeline version, and a test covers it. Phase 9 adds a trigger as a second guard.
- **Pairs are unique:** user–role, role–permission, user–group and document–group each have one row per pair.
- **Audit is append-only:** Phase 9 adds a trigger that rejects `UPDATE` and `DELETE` on `audit_events`.
- **Outbox in the same transaction:** a job, chunk save, delete or access change and its `outbox_events` row commit together, or neither does.

## 8. Seed data

Seed data is loaded by data migrations, so every environment gets exactly the same set. No default passwords are ever seeded. The first Admin is created with `python manage.py bootstrap_admin --username <name>`, which asks for a password and sets up MFA.

| Table | Rows |
|---|---|
| `roles` | User · Knowledge manager · Pipeline engineer · Evaluator · Release approver · Admin (all `is_system = true`) |
| `permissions` (19) | `rag.ask`, `documents.view`, `feedback.create`, `documents.upload`, `documents.manage`, `documents.manage_access`, `jobs.view`, `jobs.retry`, `pipelines.view`, `pipelines.edit`, `indexes.view`, `indexes.build`, `evaluation.view`, `evaluation.manage_datasets`, `evaluation.run`, `failures.review`, `releases.approve`, `accounts.manage`, `audit.read` |
| `role_permissions` | As in the role table in [01-backend.md](01-backend.md#22-accounts) |
| `access_groups` | `general`; every new user is added to it unless an Admin chooses otherwise |
| `users` (Phase 8, `evaluation 0003`) | `svc-evaluation`: service account, no password, cannot sign in, Evaluator role, member of every access group |
| `component_definitions` | The allow-list in [01-backend.md](01-backend.md#23-registry) |
| `model_definitions` | `qwen2.5:3b` (LLM, Ollama) · `qwen2.5:1.5b` (LLM, Ollama) · `multilingual-e5-small` (embedding, 384 dimensions) · `ms-marco-MiniLM-L6-v2` (reranker) |
| `retrieval_definitions` | `baseline`: dense top 20 · BM25 top 20 · RRF k = 60 · rerank top 15 · context ≤ 4 chunks and ≤ 1,500 tokens · minimum rerank score (set from measurements in Phase 7) |
| `generation_definitions` | `grounded-v1`: `qwen2.5:3b` · temperature 0.1 · ≤ 400 output tokens · citations required · abstain when there is no evidence |
| `pipeline_definitions` · `pipeline_versions` · `pipeline_steps` | `default` (active), version 1 as `DRAFT`, with the baseline steps 1–10 |

## 9. MinIO: file contents

- **Addresses:** the S3 API is at `127.0.0.1:9000` and the MinIO web console at `127.0.0.1:9001`.
- **Credentials:** the backend uses an **app user** (`rag-app`) whose policy allows only get, put, delete and list on the three buckets below. The root credentials are used only for setup.

| Bucket | Holds | Key layout | Versioning |
|---|---|---|---|
| `rag-originals` | Uploaded files | `documents/<document_id>/v<n>/<sha256>.<ext>` | on |
| `rag-artifacts` | Docling JSON, page text, OCR output | `<document_version_id>/<job_id>/<artifact_name>` | on |
| `rag-exports` | Evaluation reports | `evaluations/<run_id>/<file>` | on |

- **Keys:** keys are always generated by the server; the user's filename is stored only in `documents.filename`.
- **Deleting bytes:** objects are deleted only after the lifecycle checks pass, i.e. no retained version or published generation needs them.

## 10. Qdrant: dense vectors

| Item | Value |
|---|---|
| Address | `127.0.0.1:6333` (HTTP) · API key required |
| Collection | `rag_chunks_g<NNNN>`, one per index generation (name stored in `index_generations.qdrant_collection`) |
| Vectors | size **384** (`multilingual-e5-small`), distance **Cosine**, HNSW defaults (`m = 16`, `ef_construct = 100`) |
| Point ID | `chunks.id` (UUID), also kept in `index_memberships.qdrant_point_id` and `embedding_records.vector_point_id` |
| Payload | `chunk_id`, `document_id`, `document_version_id`, `index_generation_id`, `page_start`, `page_end`, `section_path`, `content_hash`, `access_groups` · **no chunk text**: text is read from PostgreSQL by chunk ID |
| Payload indexes | keyword: `document_id`, `document_version_id`, `index_generation_id`, `access_groups` · integer: `page_start` |
| Memory | `on_disk_payload = true` to save RAM |
| Rule | One embedding model revision and vector size per collection. A new model means a new generation. |

**Every search** carries the mandatory filter `access_groups` matches any of the user's groups.

## 11. OpenSearch: BM25 text search

| Item | Value |
|---|---|
| Address | `https://127.0.0.1:9200` · single node · heap 512 MB · TLS · service user `rag_app`, allowed only on `rag_chunks_*` |
| Index | `rag_chunks_v<NNN>`, one per index generation (name stored in `index_generations.opensearch_index`) |
| Settings | 1 shard, 0 replicas; `refresh_interval: -1` while building, then `1s` before validation |
| `_id` | `chunks.id`, also kept in `index_memberships.opensearch_document_id` |
| Mappings (`dynamic: strict`) | keyword: `chunk_id`, `document_id`, `document_version_id`, `index_generation_id`, `content_hash`, `access_groups` · text (standard analyzer): `text_content` · text + keyword: `filename`, `section_path` · integer: `page_start`, `page_end` |
| Query shape | `bool` → `must: match text_content` · `filter: [term index_generation_id, terms access_groups]` |
| Scoring | BM25 baseline. Language analyzers and exact-match boosts only if evaluation shows a gain. |

`access_groups` always goes in the `filter` clause, never in `should`, so it cannot be outscored.

## 12. Redis: transient only

| Item | Value |
|---|---|
| Address | `127.0.0.1:6379`, `requirepass` set |
| Database 0 | Celery broker |
| Database 1 | Django cache: rate-limit counters, `/auth/me/` cache, optional answer cache |
| Memory | `maxmemory 256mb`, `maxmemory-policy volatile-lru`: only keys with a TTL (cache entries) can be evicted, never Celery messages |

## 13. How long we keep data (proposed)

| Data | Keep | Cleanup |
|---|---|---|
| `user_sessions` | 30 days after expiry or revocation | `accounts.purge_expired_sessions`, daily |
| `outbox_events` (dispatched) | 7 days | `core.purge_dispatched_outbox`, daily |
| `retrieval_runs`, `retrieval_results`, `answer_records` | 180 days, except runs linked to feedback, failure cases or evaluations (decide in Phase 7) | monthly job |
| `audit_events` | at least 1 year; never edited | none in the first release |
| Retired index generations | until the next publish has been live for 7 days and nothing references them | drop the Qdrant collection and OpenSearch index; keep the PostgreSQL row |
| MinIO old object versions | 30 days | MinIO lifecycle rule |

## 14. Backup and restore

| What | How | When |
|---|---|---|
| PostgreSQL | `pg_dump -Fc rag_platform` to `~/rag-data/backups/pg/`, keep 14 | nightly |
| MinIO | versioned buckets + `mc mirror` to an external disk | nightly |
| Copy off the machine | both backup folders to an external disk | weekly |
| Qdrant, OpenSearch | not backed up: rebuilt from the canonical chunks in PostgreSQL | after a restore |

- Point-in-time recovery (WAL archiving) is optional on one machine; nightly dumps lose at most one day.
- Phase 9 includes a **restore drill**: restore both stores onto an empty machine state, rebuild both indexes, and ask a known question.
