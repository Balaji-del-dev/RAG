# Phase 9: Hardening & daily use

## Goal

The platform is safe, observable, backed up and easy to start on this machine:
- one command starts everything in the right order;
- the console is served by Django on one origin;
- the security checklist is complete;
- a restore drill has passed.

This phase reaches **Milestone M5: ready for daily use**.

## Before you start

- Phase 8 is done: releases go through evaluation and approval.

## Tasks

### Serve the console from Django
- [ ] Add `whitenoise` to [requirements.txt](../../../requirements.txt). Pin the current release and check it with a pip dry run.
- [ ] Serve `console/dist/` at `/`, the API at `/api/`, and a catch-all view that returns `index.html` for client routes.
- [ ] `npm run build` is part of the release steps. `DEBUG = false`.

### Start, stop and modes
- [ ] systemd **user** units (`~/.config/systemd/user/rag-*.service`) for:
  - MinIO, Qdrant, OpenSearch and Ollama;
  - the API, the outbox dispatcher, the Celery worker, Celery beat and Flower.

  Each unit restarts on failure and logs to `~/rag-data/logs/`. PostgreSQL and Redis stay as system services.
- [ ] Two targets, matching the memory rule in [dependency.txt](../../../dependency.txt):
  - `rag-chat.target`: everything **except** the Celery worker;
  - `rag-ingest.target`: everything, with the worker.
- [ ] Write a short runbook in `docs/runbook.md`: start, stop, switch modes, check health, read logs, retry a job, roll back a generation, restore.

### Security checklist
- [ ] `ss -ltn`: every platform port is on `127.0.0.1`.
- [ ] Each service has its own credentials. `backend/.env` has mode 600 and is not in git (`git log -p | grep -i secret` finds nothing).
- [ ] `python manage.py check --deploy` passes, apart from items you write down with a reason, such as HSTS on localhost.
- [ ] Security headers:
  - CSP `default-src 'self'`;
  - `X-Frame-Options: DENY`;
  - `Referrer-Policy: same-origin`;
  - `X-Content-Type-Options: nosniff`.
- [ ] Database guards:
  - a trigger blocks `UPDATE` and `DELETE` on `audit_events`;
  - a trigger blocks changes to `PUBLISHED` pipeline versions.
- [ ] Review against the OWASP Top 10 for LLM apps, especially:
  - prompt injection (the Phase 7 tests);
  - sensitive information disclosure (access filters, log contents);
  - excessive agency (the LLM has no tools).
- [ ] Logs never contain passwords, session keys or tokens. Questions and answer text are logged only if the policy allows it; otherwise mask them with Presidio.
- [ ] Review the dependencies: `pip list --outdated` and `npm audit`. Upgrade, or write down why not.
- [ ] Only if other machines must reach the platform: put Caddy or nginx with TLS in front of `127.0.0.1:8000`, and keep every other port private.

### Observability
- [ ] Every log line has `request_id`, `user_id` and `trace_id`. Rotate logs with `logrotate`.
- [ ] Admin-only report pages, or saved SQL queries, from `retrieval_runs` and `answer_records`:
  - p50 and p95 latency;
  - abstention rate;
  - feedback score;
  - failures by type.
- [ ] Flower is used for queue depth, retries and failed tasks.

### Performance on this CPU
- [ ] Measure again, and compare with Phases 5 and 7:
  - ingest time for the 50-page PDF;
  - answer p50 and p95;
  - peak RAM in chat mode and in ingest mode.
- [ ] Tune within the gates, and keep a change only if an evaluation run confirms quality held:
  - `num_ctx`;
  - the number of rerank candidates (10–20);
  - the number of context chunks (3–4);
  - embedding batch size;
  - `OMP_NUM_THREADS`;
  - `qwen2.5:1.5b` vs `3b`.

### Backups and restore drill
- [ ] Nightly `pg_dump -Fc` (keep 14) and MinIO `mc mirror` to `~/rag-data/backups/`; a weekly copy to an external disk.
- [ ] **Restore drill:**
  1. restore PostgreSQL and MinIO into a fresh state;
  2. rebuild both indexes from the canonical chunks;
  3. validate;
  4. ask a known question and get the same cited answer.

## Done when

- [ ] After a cold reboot, `systemctl --user start rag-chat.target` brings the platform up, and `/api/v1/health/` is all green.
- [ ] The security checklist above is fully ticked, or each open item has a written reason.
- [ ] The restore drill has passed, and its date is recorded in the runbook.
- [ ] Performance numbers are recorded in the runbook.

## Risks and tips

- Do not add new features in this phase. Anything new goes into a later pipeline version and through Phase 8's evaluation and release.
