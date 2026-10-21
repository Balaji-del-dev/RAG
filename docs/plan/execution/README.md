# Execution plan: phases 0–9

This folder sets the build order. Each phase gives a working, testable step. A later phase is never needed to test an earlier one.

## Phases

| # | Phase | Backend apps | Console pages | Needs | Rough size* | Status |
|---|---|---|---|---|---|---|
| 0 | [Machine setup](phase-00-machine-setup.md) | — | — | — | 1–2 days | Done (2026-10-21) |
| 1 | [Backend foundation](phase-01-backend-foundation.md) | `core`, `accounts` (user model only) | — | 0 | 3 days | Done (2026-10-21) |
| 2 | [Identity & access + console shell](phase-02-identity-access.md) | `accounts` | Login, MFA, layout, account, admin pages | 1 | 5 days | Done (2026-10-21) |
| 3 | [Pipeline registry](phase-03-pipeline-registry.md) | `registry` | Pipelines, version editor | 2 | 3 days | Done (2026-10-21) |
| 4 | [Documents & upload](phase-04-documents-upload.md) | `documents` | Documents, upload, document detail | 2, 3 | 4 days | Done (2026-10-21) |
| 5 | [Processing pipeline](phase-05-processing.md) | `processing` | Job timeline, retry | 4 | 6 days | Done (2026-10-21) |
| 6 | [Indexing](phase-06-indexing.md) | `indexing` | Indexes | 5 | 5 days | Done (2026-10-21) |
| 7 | [Retrieval & chat](phase-07-retrieval-chat.md) | `retrieval` | Chat, citations, feedback, history | 6 | 7 days | Done (2026-10-21) |
| 8 | [Evaluation & release](phase-08-evaluation-release.md) | `evaluation` | Evaluation, datasets, runs, failures, approval, audit log | 7 | 5 days | Done (2026-10-21) |
| 9 | [Hardening & daily use](phase-09-hardening.md) | all | all | 8 | 4 days | In progress |

**Progress (2026-10-21):** phases 0–8 are built and tested (backend unit + integration tests against the real local services, console tests, and a browser run of every role's pages). Phase 9 is in progress:
- **Done:** every process runs as its own systemd user service (`backend/dev.sh`), security headers, database guards (append-only audit log, frozen published pipeline versions), nightly Celery beat jobs, and the `manage.py backup` command.
- **Still open:** serving the built console from Django (whitenoise), a Content-Security-Policy, the restore drill, a dependency audit, and recorded performance numbers.

**Built ahead of plan (2026-10-20):** the models and migrations for all 42 tables exist already, so Django admin can show every table. Phases 3–8 still add their seed data, services, tasks, API endpoints and console pages; tick the "Models" task in each phase file once its tests cover them.

\* For one developer, a rough estimate: about 43–44 working days, or roughly 9 weeks. Update the **Status** column as you go: `Not started` → `In progress` → `Done`.

```
0 ─► 1 ─► 2 ─┬─► 3 ─┐
             └──────┴─► 4 ─► 5 ─► 6 ─► 7 ─► 8 ─► 9
```

## Milestones

| Milestone | At the end of | What you can show |
|---|---|---|
| **M1: Sign-in works** | Phase 2 | Six roles sign in; each sees only its menu; forbidden API calls return 403 |
| **M2: Documents are searchable** | Phase 6 | An uploaded PDF is parsed, chunked, embedded and published in both indexes, filtered by access group |
| **M3: First grounded answer** | Phase 7 | A question gets a cited answer from local models, or an honest abstention |
| **M4: Measured release** | Phase 8 | A pipeline change is evaluated against the baseline and approved by someone other than its author |
| **M5: Ready for daily use** | Phase 9 | One command starts everything; backups and a restore drill have passed; security checklist done |

## How each phase file is written

Every phase file has the same sections:

1. **Goal:** what is true when the phase is finished.
2. **Before you start:** what must already work.
3. **Tasks:** checkboxes grouped by backend, database, console and tests. Tick them in the file as you go.
4. **Done when:** the checks that close the phase.
5. **Risks and tips.**

## Working rules for every phase

- **One branch per phase:** `phase-NN-short-name`, for example `phase-04-documents-upload`. Merge it to `main` when the phase is done.
- **Small commits.** Migrations are committed together with the model change that needs them.
- **Secrets never go in git:**
  - `.env` files are listed in `.gitignore`;
  - only `.env.example` (with placeholder values) is committed.
- **Keep the docs in step with the code.** If the code has to differ from these plans or the diagrams, change the docs in the same branch.

## Definition of done (applies to every phase)

- [ ] `pytest` passes; `ruff check`, `ruff format --check` and `mypy` are clean.
- [ ] `npm test`, `npm run lint` and `npx tsc --noEmit` pass (from Phase 2 on).
- [ ] Every new endpoint has a permission and tests for 401, 403 and success.
- [ ] Every state change writes an `audit_events` row, and every background action goes through `outbox_events`.
- [ ] New settings are added to `.env.example` and to [01-backend.md](../01-backend.md#3-settings--environment-variables).
- [ ] The OpenAPI schema (`/api/schema/`) matches [04-api.md](../04-api.md), or the doc is updated.
- [ ] Every new or changed page has been checked in a real browser at 1440 px and 390 px wide.
- [ ] This page's **Status** column is updated.
