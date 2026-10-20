# Build plan — Offline Hybrid RAG Platform

This folder turns the architecture in [../README.md](../README.md) into a build plan. It covers:

- what we build;
- where each part lives;
- the order we build it in.

Everything runs end to end on **one local machine, CPU only**: no GPU, no Docker, and every service listens on `127.0.0.1`. The machine, its limits and every non-Python dependency are listed in [dependency.txt](../../dependency.txt). The Python packages are in [requirements.txt](../../requirements.txt).

## What is in this folder

| File | What it answers |
|---|---|
| [01-backend.md](01-backend.md) | The Django project: folders, settings, the **8 apps** and what each one owns, authentication and authorization, Celery tasks, the processes we run |
| [02-frontend.md](02-frontend.md) | The React app in `console/`: pages, who may open them, folders, how it signs in and calls the API |
| [03-database.md](03-database.md) | PostgreSQL (42 tables, grouped by app), status values, migrations, seed data, plus MinIO, Qdrant, OpenSearch and Redis |
| [04-api.md](04-api.md) | Every REST endpoint: method, path, required permission, what it does |
| [execution/](execution/README.md) | **Phases 0–9**: the build order, the tasks in each phase, the tests, and when a phase counts as done |

**Reading order:** this page → backend → database → frontend → API → execution.

## Repository layout

```
Architechure/
├── backend/            # Django + DRF project and Celery tasks       → 01-backend.md
├── console/            # React app (Vite + TypeScript) — the frontend → 02-frontend.md
├── docs/
│   ├── README.md       # architecture, findings, schema additions
│   ├── images/ src/    # the six architecture diagrams
│   ├── concepts/       # 27 interview lessons
│   └── plan/           # this build plan
├── requirements.txt    # Python packages (CPU-only PyTorch)
└── dependency.txt      # services, system packages, models, npm packages
```

`backend/` and `console/` are empty today. Phase 1 creates the Django project and Phase 2 creates the React app ([execution/](execution/README.md)).

## The system in one picture

```
 Browser ──► console (React)  ──same origin: /api/* ──►  Django API  (uvicorn, 127.0.0.1:8000)
                                                            │  reads/writes
                                                            ├──► PostgreSQL   system of record (42 tables)
                                                            ├──► MinIO        file bytes (3 buckets)
                                                            ├──► Qdrant       dense search  ┐ derived indexes,
                                                            ├──► OpenSearch   BM25 search   ┘ rebuildable
                                                            └──► Ollama       LLM (qwen2.5:3b) through LiteLLM

 outbox_events (PostgreSQL) ──► outbox dispatcher ──► Redis ──► Celery worker
                                                                  queues: ingest · index · evaluation
                                                                  parse → OCR → chunk → embed → index → validate
```

## The main decisions

| # | Decision | Why |
|---|---|---|
| 1 | One machine, CPU only; every service listens on `127.0.0.1`. | That is the target machine (Intel i3, 7.5 GB RAM). Nothing is exposed to the network. |
| 2 | One Django project with **8 apps** and one PostgreSQL database (a "modular monolith"). | One deployment is in scope. Separate apps keep the code areas apart without running separate services. |
| 3 | The React console is served from the **same origin** as the API: through the Vite proxy in development, and by Django in production. | The session cookie and CSRF token then work with no CORS setup, and no tokens are kept in browser storage. |
| 4 | Server-side sessions; roles and permissions in our own tables; document access groups as a **mandatory filter** in both search engines. | Permissions are enforced by the server and by the search query, never by the UI or the LLM. |
| 5 | An `outbox_events` table plus a dispatcher process, instead of `transaction.on_commit`. | Background tasks are never lost if a process dies right after a commit. |
| 6 | One Celery worker, `--concurrency=1`, serving the `ingest`, `index` and `evaluation` queues. | Keeps memory within 7.5 GB. |
| 7 | Ollama only, called through the LiteLLM Python library. `qwen2.5:3b` is the default and `qwen2.5:1.5b` the low-memory fallback. vLLM is not used. | vLLM is built for GPUs. |
| 8 | Langfuse is not used on this machine. Traces stay in PostgreSQL (`retrieval_runs`, `answer_records`) and in JSON logs. | Self-hosted Langfuse needs Docker and ClickHouse, which is too heavy here. |
| 9 | PostgreSQL decides which index generation is live (`index_generations.status = PUBLISHED`). | Qdrant and OpenSearch cannot switch together; one database commit can. |
| 10 | Build the **baseline** retrieval first. Query rewriting, HyDE, multi-query and the like come only when evaluation shows a gain. | We can measure every change against the baseline. |

## Fixed while planning

1. **Author of a pipeline version.** Release approval needs "the approver is never the author". The schema had no author column, so the check was impossible. I added `pipeline_versions.created_by`, and the schema diagram now shows it.
2. **Where roles and permissions live.** Some docs said "Django Groups", but the schema has its own `roles`, `permissions`, `role_permissions` and `user_roles` tables. The plan uses the schema's tables, with a custom auth backend so `user.has_perm("rag.ask")` still works. [../README.md](../README.md), the data diagram and [requirements.txt](../../requirements.txt) now say the same.

## Still to decide

| Question | Default in this plan | Decide by |
|---|---|---|
| Will people use it from other machines on the network? | No: localhost only. If yes, add a TLS reverse proxy (Caddy or nginx) in Phase 9. | Phase 9 |
| How long do we keep query history (`retrieval_runs`, `answer_records`)? | 180 days, then delete. | Phase 7 |
| Which documents go into the first evaluation dataset? | 30–50 questions over real documents, written with the people who own them. | Phase 8 |
| MinIO or another S3-compatible store? | Keep the installed MinIO and access it only through the S3 API ([../README.md](../README.md), finding 1). | Phase 4 |
