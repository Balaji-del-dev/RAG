# Offline Hybrid RAG Platform — Architecture (v2)

A configurable, fully local RAG platform. Files are uploaded through React and validated and orchestrated by Django. Celery workers parse, chunk, embed and index them. Questions are answered with hybrid retrieval and grounded, cited generation from local models.

| Layer | Technology | Responsibility |
|---|---|---|
| Frontend | React | Upload, document management, pipeline settings, chat, evaluation UI |
| Application | Django + DRF | APIs, business logic, orchestration |
| System of record | PostgreSQL | Configuration, document lifecycle, chunks, jobs, index state, results |
| Object storage | MinIO (S3 API) | Originals, extracted artifacts, OCR output, generated files |
| Dense retrieval | Qdrant | Vectors, ANN search, payload filters |
| Lexical retrieval | OpenSearch | BM25, full-text and exact keyword search |
| Async execution · broker · monitoring | Celery · Redis · Flower | Parsing, OCR, chunking, embedding, indexing, evaluation |
| LLM gateway · inference | LiteLLM · Ollama or vLLM | One local model interface; local generation |
| Embeddings · reranker | Local embedding model · local cross-encoder | Document and query vectors; candidate reranking |
| Parsing · OCR | Docling + PyMuPDF · Tesseract + EasyOCR | Text, layout, tables; scanned pages |
| Evaluation · tracing | DeepEval · Langfuse | Quality tests; request and model-call traces |

**Scope:**
- **In scope:** upload-only ingestion, one application deployment.
- **Out of scope:** external connectors, web-search fallback, multi-tenancy, Docker, Kubernetes, CI/CD platform, Prometheus, Logstash/ELK.

**Rules:**
1. PostgreSQL is the source of truth for metadata and lifecycle state.
2. MinIO is the source of truth for file contents.
3. Qdrant and OpenSearch are derived indexes.
4. Django coordinates; Celery runs the long work.
5. Publication waits for both search systems to pass validation.
6. An LLM's text is not proof of grounding.
7. Everything runs from locally available files.

---

## Learning path — concepts for interviews

**[concepts/index.html](concepts/index.html)** — 27 lessons in one order (about 11 hours), written in simple English for interview preparation. Each lesson is its own HTML page with Previous / Next navigation and a "mark as learned" tracker.

Every lesson has the same structure: **What is it?** (the formal interview answer plus "in simple words") → **Why do we need it?** → **How does it work?** (numbered steps with examples and a diagram) → **Example: step by step** → **Important terms** → **Types and comparison** → **Advantages and limitations** → **Where is it used?** (real examples and our platform) → **How to explain it in an interview** (a 1-minute spoken answer, plus "don't say / say instead") → **Interview questions and answers** (model answers shown, with a practice mode that hides them) → **Quick revision**.

| Stage | Lessons |
|---|---|
| 1 · Foundations | 01 How LLMs work · 02 Tokens & tokenization · 03 Embeddings & similarity · 04 Transformer & attention · 05 Decoding: temperature, top-p · 06 Running models locally · 07 Prompt engineering |
| 2 · Ingestion pipeline | 08 RAG fundamentals · 09 Document parsing & OCR · 10 Cleaning & metadata · 11 Chunking strategies · 12 Embedding models · 13 Vector databases & HNSW · 14 Keyword search & BM25 |
| 3 · Retrieval & answers | 15 Query transformation · 16 Hybrid search & RRF · 17 Reranking · 18 Grounded answers & hallucination · 19 Agents, tools & GraphRAG |
| 4 · Quality | 20 Evaluating RAG · 21 Observability & tracing |
| 5 · Safety & production | 22 Guardrails · 23 LLM security & prompt injection · 24 Privacy & data governance · 25 Production: latency, cost, scale · 26 Fine-tuning, LoRA & RLHF · 27 System design: the full RAG system |

Three pages sit next to the lessons:

- **[concepts/rag-flow.html](concepts/rag-flow.html)** — production RAG on one page, in build order. It runs: plan → ingestion and sync → parsing → OCR → cleaning, metadata and PII → chunking → enrichment → embedding → indexing → query understanding → hybrid search and RRF → reranking → context engineering → grounded generation → guardrails → security and access → evaluation → observability → latency, cost and caching → reliability → versioning and releases → feedback loop. Each step explains how it works and has a checklist of **Mandatory** and **Good to have** practices, with a "Mandatory only" filter. It includes formulas with worked examples (BM25, RRF, InfoNCE, precision@k, recall@k, MRR, nDCG, faithfulness), the OWASP LLM Top 10, a production readiness checklist, a debugging table, and what this platform does or does not do yet.
- **[concepts/interview-questions.html](concepts/interview-questions.html)** — all 277 questions with model answers and key words; filter by stage and level, search, mark questions as known, and practise with flashcards.
- **[concepts/revision.html](concepts/revision.html)** — every lesson's interview definition and five key points on one page, for the day before an interview.

The interview content lives in `concepts/assets/qa/NN.js` (one file per lesson); `concepts/assets/path.js` holds the lesson order and renders navigation, questions and revision cards.

## RAG Handbook — every concept, explained

**[handbook/index.html](handbook/index.html)** explains 710 concepts in 24 sections. It covers RAG foundations, ingestion, parsing, chunking, embedding, indexing, query understanding, rewriting and assembly, retrieval, hybrid fusion, reranking, context assembly, context windows, memory, generation, advanced RAG, guardrails and security, evaluation, production and ops, tools, LLM internals, fine-tuning, and system architecture.

Each concept has the same parts: **in simple words**, **how it works**, **where to use it**, **the real-world problem it solves**, **a real-time example**, and, for 136 of them, **simple code**.
- The start page has the whole tree, a suggested learning order, and search across all concepts.
- Each section page has a filter.
- The content lives in `handbook/data/NN.js`, one file per section; `handbook/assets/handbook.js` renders the pages.

---

## Build plan

**[plan/README.md](plan/README.md)** turns this architecture into a plan for building it on one local CPU-only machine:

- **[plan/01-backend.md](plan/01-backend.md):** the Django project in `backend/`, its 8 apps (`core`, `accounts`, `registry`, `documents`, `processing`, `indexing`, `retrieval`, `evaluation`), authentication and authorization, Celery tasks and processes.
- **[plan/02-frontend.md](plan/02-frontend.md):** the React console in `console/`: pages per role, sign-in, streamed chat, uploads.
- **[plan/03-database.md](plan/03-database.md):** the 42 PostgreSQL tables by app, status values, migration order, seed data, and the MinIO, Qdrant, OpenSearch and Redis setup.
- **[plan/04-api.md](plan/04-api.md):** every endpoint, with its permission.
- **[plan/execution/](plan/execution/README.md):** phases 0–9 with tasks, tests and "done when" checks, from machine setup to daily use.

---

## Diagrams

### 1. System architecture
![System architecture](images/01-system-architecture.png)

The seven groups from the brief, laid out so their lines don't cross. Django sits above three columns: Celery processing, the two derived indexes, and the online RAG flow. Below them are the durable data layer and then quality & operations. An **Identity & access** row inside Django shows authentication, sessions, role-based authorization, document access control and service credentials; the online flow starts with *Authenticate & validate* and *Resolve access scope*.

### 2. Data & storage architecture
![Data and storage architecture](images/02-database-architecture.png)

- **What each store owns:** the MinIO bucket and key layout, the PostgreSQL table groups (4.1–4.7), the outbox → Redis → Celery dispatch path, and the Qdrant and OpenSearch collection/index specs, including the `access_groups` filter field.
- **Identity map:** which ID appears in which store, including Langfuse, `user_id` and `access_groups`.
- **Status lifecycles.**
- **Four paths:** write, publish, read, and change/delete.

### 3. PostgreSQL schema
![Database schema](images/03-database-schema.png)

The brief's section 4 plus a 4.7 identity & access group: 42 tables and 51 foreign keys, with columns, types, nullability, keys and the recommended indexes. Additions beyond the brief are highlighted in the image: **+** marks added columns, **ADDED** marks an added table.

### 4. Ingestion & indexing flow
![Ingestion flow](images/04-ingestion-flow.png)

### 5. Online retrieval & generation flow
![Query flow](images/05-query-flow.png)

### 6. Evaluation & continuous improvement loop
![Evaluation loop](images/06-evaluation-loop.png)

---

## Findings that change the plan

These came from checking each new component against the brief's constraints (offline, no Docker, one deployment).

1. **MinIO community edition is no longer distributed as binaries.** Since October 2025 it has been source-only, and its repository was later archived. Existing deployments keep working, but patches aren't shipped. Options:
   - pin a release you build and verify yourself, or
   - use another S3-compatible store (SeaweedFS, Garage, Ceph RGW).

   Keep Django and Celery on the S3 API (boto3 / django-storages) so the swap is a configuration change.
2. **Langfuse v3 conflicts with "no Docker".** Self-hosted v3 needs PostgreSQL, ClickHouse, Redis/Valkey and S3 blob storage, plus separate web and worker processes. It is shipped as Docker Compose (single VM, no high availability or backups) or Kubernetes (Helm). Decide before building:
   - allow a container exception for Langfuse only,
   - run it from source with its own ClickHouse (unsupported path), or
   - start with traces in PostgreSQL (`retrieval_runs.trace_id`, latencies, token usage) and add Langfuse later.

   Langfuse's S3 store could be a separate MinIO bucket.
3. **Dispatching Celery tasks from `transaction.on_commit` can lose tasks.** If the process dies after COMMIT but before Redis receives the task, the task is gone. The design adds an `outbox_events` table, written in the same transaction as the job or chunk rows:
   - a dispatcher claims rows with `SELECT … FOR UPDATE SKIP LOCKED` and publishes them;
   - tasks are idempotent, so a double dispatch is harmless.

   This implements the brief's "transactional outbox or durable dispatch mechanism".
4. **DeepEval works offline.** Its LLM judge can be a local Ollama model. Small judges are noisier, so:
   - calibrate the judge against human-labelled cases;
   - keep the judge model fixed across compared runs.

## Additions to the brief's schema

| Addition | Why |
|---|---|
| `pipeline_versions.retrieval_definition_id`, `.generation_definition_id` | The brief defines both tables, but nothing references them. A run must record which retrieval and generation settings it used. |
| `chunks.pipeline_version_id` | Re-processing one document version with a new pipeline would otherwise collide on `(document_version_id, chunk_index)`. The unique key becomes `(document_version_id, pipeline_version_id, chunk_index)`. |
| `processing_jobs.created_at`, `retrieval_runs.created_at` | The brief's recommended indexes use these columns. |
| `outbox_events` table | Durable Celery dispatch and index sync (finding 3). |
| 4.7 identity & access tables: `users`, `user_sessions`, `roles`, `permissions`, `role_permissions`, `user_roles`, `access_groups`, `user_access_groups`, `document_access_grants` | The brief has no authentication or authorization model. See the next section. |
| `documents.created_by`, `retrieval_runs.user_id`, `user_feedback.user_id`, `pipeline_versions.created_by` + `published_by`, `evaluation_runs.approved_by`, `audit_events.actor_user_id` + `ip_address` | Record who uploaded, asked, authored, published, approved and changed what. `pipeline_versions.created_by` lets the release approval check that the approver is not the author. |

Two further recommendations:
- **Chunk IDs:** `uuid5(namespace, document_version_id · pipeline_version_id · chunk_index · content_hash)`, used directly as the Qdrant point ID and the OpenSearch `_id`. Qdrant accepts only UUIDs or unsigned integers as point IDs. Retries then produce the same IDs, so they never duplicate records.
- **Which generation is live:** decided by one PostgreSQL commit (`index_generations.status = PUBLISHED`). Qdrant and OpenSearch can each switch an alias atomically, but not both together. So the query path reads the physical collection and index names from PostgreSQL; aliases are for operators only.

## Authentication & authorization

**Authentication — who are you?**
- Django authentication with a custom user model (`users`). Local accounts store Argon2 password hashes; LDAP / Active Directory sign-in is optional (`auth_source`).
- Server-side sessions (`user_sessions`): HttpOnly + Secure + SameSite cookie, a CSRF token on every write, idle and absolute timeouts, and revocation on logout or by an admin.
- Lockout after repeated failed sign-ins (`failed_login_count`, `locked_until`); optional MFA (TOTP), which can be required for admins with `MFA_REQUIRED_FOR_ADMINS=true`.

**Authorization — what may you do?**

| Role | May do |
|---|---|
| User | ask questions; open cited documents in their access groups; give feedback |
| Knowledge manager | upload, version and delete documents; set each document's access groups |
| Pipeline engineer | edit draft pipeline versions, models, retrieval and generation settings; start index builds |
| Evaluator | manage evaluation datasets; run evaluations; review failure cases |
| Release approver | approve and publish a validated pipeline and index generation — never their own change |
| Admin | manage users, roles, access groups and sessions; read the audit log |

Roles and permissions are the schema's own tables (`roles`, `permissions`, `role_permissions`, `user_roles`). A custom Django authentication backend answers `user.has_perm("rag.ask")` from them, and DRF permission classes call it on every endpoint. Django's built-in group tables stay unused.

**Document access control.** Each document is shared with one or more access groups (`document_access_grants`). The index builder copies them into the Qdrant payload and an OpenSearch keyword field (`access_groups`). Every search adds the user's groups — read from the session, never from the request — as a mandatory filter in **both** engines, so text a user may not read never reaches the LLM. Granting or revoking access writes an `index.acl` outbox event that rewrites the field in both indexes. Citations, downloads and answer caches are checked against the same scope.

**Service credentials.** PostgreSQL, Redis, MinIO, Qdrant, OpenSearch, Ollama and LiteLLM stay on the private network (localhost on a single machine), each with its own credentials from environment variables. Ollama has no login, so it must never listen on a public interface.

**Audit.** `audit_events` records sign-ins, failed sign-ins, role and access-group changes, uploads, publications and deletions, with `actor_user_id` and `ip_address`.

## Index publication sequence

1. Build the new Qdrant collection and OpenSearch index for the generation.
2. Compare expected and actual chunk counts.
3. Check for missing, duplicate and orphaned records.
4. Run representative dense, lexical and hybrid searches; record the results in `index_validations`.
5. Mark the generation published only after both indexes pass.
6. Keep the previous generation for rollback until nothing references it.

## Retrieval order (baseline)

1. Qdrant dense search and OpenSearch BM25 search, in parallel.
2. Normalize and dedupe the candidates.
3. RRF fusion (k = 60).
4. Cross-encoder reranking.
5. Optional MMR and parent expansion.
6. Context budget.
7. Source and evidence validation.
8. Grounded generation through LiteLLM.
9. Schema, citation and grounding checks, or abstain.

Query rewriting, multi-query, HyDE, decomposition, corrective retrieval and agentic routing are enabled only when the evaluation loop shows a gain.

---

## Files

```
docs/
├── README.md
├── plan/                      # build plan: backend, frontend, database, API, execution phases 0–9
├── runbook.md                 # start/stop, URLs, roles, everyday tasks, backup and restore
├── concepts/                  # 27 interview lessons + question bank + revision page
├── images/                    # rendered PNGs (2× scale)
│   ├── 01-system-architecture.png
│   ├── 02-database-architecture.png
│   ├── 03-database-schema.png
│   ├── 04-ingestion-flow.png
│   ├── 05-query-flow.png
│   └── 06-evaluation-loop.png
├── src/                       # editable sources
│   ├── 01…06 *.html           # diagram pages (03 is generated)
│   ├── build_schema.py        # table spec → 03-database-schema.html
│   ├── _schema-template.html  # ER page shell + FK line router
│   ├── diagram.css · flow.css · diagram.js
│   ├── viewer.js              # browser view: fit to window, wheel zoom, drag to pan
│   ├── render-dot.mjs         # Graphviz via WebAssembly (when dot/neato is not installed)
│   └── render.py              # HTML → PNG with Playwright
```

**Viewing in a browser:** open any `docs/src/0*.html` page. It opens fitted to 100% of the window width and height, with no scrollbars.

| Action | Control |
|---|---|
| Zoom at the cursor | mouse wheel |
| Pan | drag |
| Toggle fit / actual size | double-click |
| Fit · actual size · zoom | keys `0` · `1` · `+` / `-`, or the toolbar at the bottom right |

To regenerate:

```bash
pip install playwright && playwright install chromium
cd docs/src && npm i @hpcc-js/wasm-graphviz && cd -   # only if Graphviz is not installed
python3 docs/src/build_schema.py    # after editing TABLES / EDGES / LAYOUT
python3 docs/src/render.py          # all images; or e.g. `render.py 03`
```

## Sources

- MinIO community edition becomes source-only — https://linuxiac.com/minio-with-yet-another-controversial-move/ · https://itsfoss.com/news/minio-moves-away-from-open-source/ · https://glukhov.org/data-infrastructure/object-storage/minio-dead/
- Langfuse self-hosting (architecture, Docker Compose vs Kubernetes) — https://langfuse.com/self-hosting · https://langfuse.com/self-hosting/docker · https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse · https://langfuse.com/changelog/2024-12-09-Langfuse-v3-stable-release
- Outbox vs `on_commit` publishing (Open edX ADR) — https://docs.openedx.org/projects/openedx-events/en/ulmo/decisions/0015-outbox-pattern-and-production-modes.html
- DeepEval with a local Ollama judge — https://docs.atla-ai.com/integrations/deepeval · https://transformerlab.ai/docs/evaluate/judge
- Qdrant collection aliases — https://qdrant.tech/documentation/manage-data/collections/ · hybrid queries — https://qdrant.tech/documentation/concepts/hybrid-queries
- OpenSearch reciprocal rank fusion — https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/rrf/
- Docling technical report — https://arxiv.org/html/2408.09869v5
