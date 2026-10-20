# Phase 1: Backend foundation

## Goal

The Django project exists in `backend/` with its settings, the 8 empty apps, the custom user model, the outbox, Celery, health checks, logging and the test and lint tooling. Nothing user-facing exists yet. Every later phase builds on this base.

## Before you start

- Phase 0 is done: every service check passes.

## Tasks

### Project
- [ ] `django-admin startproject config backend`, which creates `backend/manage.py` and `backend/config/`.
- [ ] Split the settings into `config/settings/base.py`, `local.py` and `test.py`, all reading `backend/.env` through `django-environ`.
- [ ] Write `backend/.env.example` with every variable in [01-backend.md §3](../01-backend.md#3-settings--environment-variables).
- [ ] Create the 8 apps in `backend/apps/`: `core`, `accounts`, `registry`, `documents`, `processing`, `indexing`, `retrieval`, `evaluation`. Each has `name = "apps.<app>"` and the standard file layout.
- [ ] `config/urls.py`: `/api/v1/` with one include per app; `/api/schema/` and `/api/docs/` (drf-spectacular).
- [ ] Set up `config/asgi.py`, then check it runs: `uvicorn config.asgi:application --host 127.0.0.1 --port 8000`.

### Custom user model (do this before the first `migrate`)
- [ ] `accounts.User` (`db_table = "users"`):
  - UUID primary key and every column from the schema;
  - extends `AbstractBaseUser` and `PermissionsMixin`.
- [ ] `AUTH_USER_MODEL = "accounts.User"`, with Argon2 first in `PASSWORD_HASHERS`.
- [ ] Run `python manage.py migrate` for the first time only after the two steps above.

### `core`
- [ ] `UUIDModel` and `TimeStampedModel` base classes.
- [ ] `OutboxEvent` model and the `core.outbox.emit()` helper.
- [ ] `python manage.py run_outbox`:
  - claims rows with `FOR UPDATE SKIP LOCKED LIMIT 200`;
  - publishes each to Celery and marks it `DISPATCHED`;
  - backs off on failure;
  - stops cleanly on SIGTERM.
- [ ] `core.audit.record()`. Its model, `AuditEvent`, is created in the `evaluation` app now; the rest of that app comes in Phase 8.
- [ ] Client wrappers in `core/clients/` for `storage`, `vector_store`, `search_index` and `llm`, at first only with the calls the health check needs.
- [ ] `GET /api/v1/health/` checks PostgreSQL, Redis, MinIO, Qdrant, OpenSearch and Ollama.
- [ ] Request ID middleware, the error format from [04-api.md](../04-api.md) as a DRF exception handler, and structlog JSON logging.

### DRF and Celery
- [ ] DRF defaults:
  - `SessionAuthentication`;
  - `IsAuthenticated`;
  - page-number pagination (25, max 100);
  - `django-filter`;
  - throttles stored in the Redis cache.
- [ ] `config/celery.py`:
  - queues `ingest`, `index` and `evaluation`;
  - JSON serializer only;
  - `task_acks_late`, `worker_prefetch_multiplier = 1`;
  - default retry backoff and time limits.
- [ ] A test task, `core.ping`, that the dispatcher can send.

### Tooling
- [ ] `backend/pyproject.toml` with settings for ruff, mypy (django-stubs plugin) and pytest (`DJANGO_SETTINGS_MODULE=config.settings.test`, `integration` marker).
- [ ] `tests/conftest.py` and factory-boy factories for `User`.

### Tests
- [ ] Health: `200` when all services are up; `503` naming the failing service when one is mocked down.
- [ ] Outbox: two dispatchers running at once never send the same row twice (two transactions with `SKIP LOCKED`).
- [ ] Error handler: a `ValidationError` and a 404 both return the standard error shape with `request_id`.

## Done when

- [ ] `python manage.py check` passes, and `migrate` runs on an empty database.
- [ ] `pytest`, `ruff check` and `mypy` are clean.
- [ ] `/api/v1/health/` shows all six services up, and `/api/docs/` loads.
- [ ] An outbox row for `core.ping` reaches the Celery worker, and Flower (`127.0.0.1:5555`) shows the task.

## Risks and tips

- **The custom user model is the one thing you cannot add later.** Create it before the very first `migrate`.
- Keep `core/clients/` small. Each wrapper exposes only the calls the platform needs, which keeps vendor SDKs out of the apps.
