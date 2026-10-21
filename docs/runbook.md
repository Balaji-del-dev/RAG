# Runbook: running the RAG platform on this machine

Everything runs on this computer, CPU only, on `127.0.0.1`. The build plan is in [plan/](plan/README.md).

## Addresses

| What | Address |
|---|---|
| Console (sign in here) | http://localhost:5173 (use `localhost`, not `127.0.0.1`) |
| API health | http://127.0.0.1:8001/api/v1/health/ |
| API docs (after signing in) | http://127.0.0.1:8001/api/docs/ |
| Django admin (Admin role) | http://127.0.0.1:8001/django-admin/ |
| Flower (background tasks) | http://127.0.0.1:5555 |

## Start, stop, status, logs

```bash
backend/dev.sh start      # api, outbox, worker, beat, flower, console — each a systemd user service
backend/dev.sh status
backend/dev.sh stop
backend/dev.sh restart
backend/dev.sh logs worker   # api | outbox | worker | beat | flower | console  (files: ~/rag-data/logs/)
```

- **Outside the editor:** the services (`rag-api`, `rag-worker`, …) run outside VS Code, so closing or restarting the editor does not stop them.
- **Restarts:** a crashed service restarts by itself after 5 seconds.
- **Shared services:** PostgreSQL, Redis, MinIO, Qdrant, OpenSearch and Ollama are separate system services. This project shares them with GEN, using its own database, Redis databases 2–3, buckets and `rag_chunks_*` indexes.

**Memory.** This computer has 7.5 GB of RAM.
- If it slows down, close browser tabs, or stop GEN's Django and Celery processes.
- While chatting, you can stop the worker: `systemctl --user stop rag-worker`. Start it again before uploading.

## Roles

There is one account per role: `bthangadurai` (all six roles), plus `demo-user`, `demo-knowledge-manager`, `demo-pipeline-engineer`, `demo-evaluator` and `demo-release-approver`.

Passwords are not stored in the repository. An Admin can reset them on the **Users** page, and anyone can change their own under **My account**.

## Everyday tasks

| Task | Who | Where |
|---|---|---|
| Upload a document, choose its access groups | Knowledge manager | Documents → Upload |
| See processing steps, retry a failed job | Knowledge manager, Pipeline engineer | the document's page |
| Ask questions | everyone | Chat |
| Validate an index generation | Pipeline engineer | Indexes → Validate |
| Make the first generation live; roll back | Release approver | Indexes |
| Change the pipeline | Pipeline engineer | Pipelines → clone v1 → edit the draft; then Indexes → Build for the new version |
| Release a new version | Evaluator runs it; a **different** Release approver approves | Evaluation → Start a run → open the run → Approve and publish |
| Review bad answers | Evaluator | Failures |
| Users, groups, sessions, audit log | Admin | Administration |
| Add, edit or delete any table row (not the audit log; not a published pipeline version) | Admin | http://127.0.0.1:8001/django-admin/ — every change is audited |

## Backup and restore

```bash
cd backend && ../.venv/bin/python manage.py backup    # PostgreSQL dump (keeps 14) + MinIO buckets → ~/rag-data/backups
```

Copy `~/rag-data/backups` to an external disk every week.

**Restore**, as a drill or for real:
1. `backend/dev.sh stop`
2. `pg_restore --clean -h 127.0.0.1 -U rag_user -d rag_platform ~/rag-data/backups/pg/<latest>.dump`
3. Copy `~/rag-data/backups/minio/<bucket>/` back into the bucket, for example with a short Python script using the `rag-app` login.
4. `backend/dev.sh start`, then rebuild the indexes: Indexes → Build (live pipeline version) → Validate → Publish.

Qdrant and OpenSearch are never backed up; they are rebuilt from the chunks in PostgreSQL.

## Start again with an empty library

```bash
backend/dev.sh stop                                        # stops every service
cd backend && ../.venv/bin/python manage.py backup         # first, always
../.venv/bin/python manage.py reset_content                # dry run: lists what would go
../.venv/bin/python manage.py reset_content --yes          # documents, chunks, indexes, chat, evaluation, outbox
../.venv/bin/celery -A config purge -f                     # queued background tasks
cd .. && backend/dev.sh start
```

Users, roles, access groups, pipelines and the audit log stay. After the first upload, the new index generation
must be made live: Indexes → Validate → Publish.

## Pipeline v2 (live since 2026-10-21)

Compared with v1, v2 adds:
- the document title and section to every chunk, for search and for the reranker;
- keyword search over file names and headings that forgives typos;
- up to 5 sources instead of 1–4, and a prompt that asks for complete, structured answers.

On the `cv-basics` dataset, answers held 93% of the expected facts, against 3% with v1. Retrieval stayed at hit@5 = 1.0, and the abstention case still passed. Expect about 20–40 seconds per answer on this CPU; questions asked at the same time wait their turn (up to 3 minutes).

**Releasing a later version** works the same way:
1. Pipeline engineer: Pipelines → clone → edit the draft → Indexes → **Build** for it → **Validate**.
2. Evaluator: start a run on a dataset, against the new version's generation.
3. A **different** Release approver: open the passed run → **Approve and publish**. Roll back on the Indexes page if needed.

## One-time setup commands

Already done on this machine. Run them again only to reset a login.

```bash
cd backend
MINIO_ROOT_USER=… MINIO_ROOT_PASSWORD=… ../.venv/bin/python manage.py setup_minio          # buckets + rag-app user
OPENSEARCH_ADMIN_PASSWORD=… ../.venv/bin/python manage.py setup_opensearch                # rag_app service user
../.venv/bin/python manage.py bootstrap_admin --username <name> --email <email>          # first Admin (only if none exists)
```

The admin passwords are read from the environment and never stored. Only the app logins are kept, in `backend/.env` (mode 600, not in git).

## Tests

```bash
cd backend && ../.venv/bin/python -m pytest                                  # fast tests
cd backend && ../.venv/bin/python -m pytest -m "integration or not integration"  # everything, incl. real Qdrant/OpenSearch/models
cd console && npm test && npm run lint && npx tsc -b
```
