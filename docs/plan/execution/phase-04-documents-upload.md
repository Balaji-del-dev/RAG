# Phase 4: Documents & upload

## Goal

Knowledge managers upload files of the 10 first-release formats through the console. Each upload goes through these steps, and nothing else in the platform trusts the browser:

1. The server validates the file.
2. The file is stored in MinIO.
3. The document's rows, access groups, job and outbox event are written in one transaction.
4. The job is sent to the `ingest` queue.

## Before you start

- Phase 2 is done (access groups exist) and Phase 3 is done (the pipeline version exists for the job).

## Tasks

### Backend (`documents`, `accounts`)
- [ ] Models:
  - all 5 tables of 4.2;
  - `accounts.DocumentAccessGrant` (migration `accounts 0004`, which depends on `documents 0001`).
- [ ] The storage client (`core/clients/storage.py`): put, get as a stream, delete, and version ID, all through the S3 API.
- [ ] The upload service, with checks in this order: permission and groups → extension → sniffed MIME (`python-magic`) → size → content → SHA-256 duplicate.
  - **Office files:** limits on total uncompressed size and entry count.
  - **PDFs:** must open; reject encrypted files; page limit.
  - **Duplicates:** return `200` with `duplicate: true` and the existing document.
- [ ] Store the object first, under a server-generated key, then commit one transaction:
  - `documents` and `document_versions` (the version goes `UPLOADED → VALIDATING → QUEUED`);
  - `document_access_grants`;
  - `processing_jobs` (`QUEUED`) and the outbox row `job.dispatch`;
  - the audit event.
- [ ] `processing.run_job` stub: sets the job to `RUNNING` and then `SUCCEEDED`, so the whole flow can be tested before Phase 5.
- [ ] Endpoints:
  - `documents/` (list in my scope, upload);
  - `documents/{id}/`, `…/versions/`, `…/access/` (emits `index.acl`), `…/download/` (streamed after an access check);
  - `DELETE documents/{id}/` (soft delete; emits `index.delete`).
- [ ] Selectors filter every list and detail by `access_scope(user)`. Anything out of scope gives `404`.
- [ ] Nightly beat task `documents.remove_orphan_objects`: removes objects with no database row that are older than a day.

### Console
- [ ] `/documents/upload`:
  - drag and drop or a file picker;
  - an `XMLHttpRequest` progress bar;
  - `AccessGroupPicker` (my groups, at least one);
  - the duplicate message;
  - clear errors for `413` and `415`.
- [ ] `/documents`: a `DataTable` with filename, status, version, groups and date; filters for status, type and group; a filename search.
- [ ] `/documents/:id`:
  - versions and a status timeline;
  - access groups (editable with `documents.manage_access`);
  - download;
  - delete with `ConfirmDialog`;
  - polling every 3 seconds while the document is processing.

### Tests
- [ ] Every rejection, using fixtures in `backend/tests/fixtures/`:
  - wrong extension;
  - a `.pdf` that is really an `.exe`;
  - over the size limit;
  - a zip bomb disguised as `.docx`;
  - an encrypted PDF.
- [ ] A duplicate returns the existing document. A new version of the same document works.
- [ ] Atomicity: if the transaction fails, there is no job, no outbox row and no grants. The orphaned object is then removed by the cleanup task.
- [ ] Access:
  - a user cannot assign a group they are not in;
  - a document in another group gives `404` for list, detail and download.

## Done when

- [ ] One fixture of each of the 10 formats uploads successfully and creates:
  - a MinIO object;
  - the document, version, grant and job rows;
  - an outbox row that reaches the `ingest` queue (the stub job ends as `SUCCEEDED`).
- [ ] A User who is not in the document's group cannot see it in the list, open it or download it.

## Risks and tips

- Read the upload in chunks to a temporary file, so a 50 MB file never sits fully in memory.
- Use the filename the user gave only for display, never in an object key or path.
