# Phase 6: Indexing

## Goal

Chunks are written to Qdrant and OpenSearch for an index generation, with `access_groups`. Both indexes are validated, and the generation is published in one PostgreSQL commit. Access changes and deletes reach both engines. Drift is found and repaired every night.

This phase reaches **Milestone M2: documents are searchable**.

## Before you start

- Phase 5 is done: versions reach `INDEXING`, and `index.upsert` events are emitted.

## Tasks

### Backend (`indexing`)
- [ ] Models: all 4 tables of 4.4, with a partial unique index that allows only one `PUBLISHED` generation.
- [ ] Clients:
  - `vector_store.py`: create the collection (384 dimensions, Cosine, payload indexes, `on_disk_payload`), upsert, delete by filter, set payload, count, scroll IDs, search;
  - `search_index.py`: create the index (strict mapping), bulk index, delete by query, update by query, count, search.
- [ ] Create a generation: `rag_chunks_g<NNNN>` and `rag_chunks_v<NNN>`, both recorded in `index_generations`.
- [ ] Tasks ([01-backend.md §2.6](../01-backend.md#26-indexing)):
  - `upsert_version`;
  - `delete_version`;
  - `update_acl`;
  - `build_generation` (OpenSearch `refresh_interval: -1` while building);
  - `validate_generation`;
  - `reconcile` (nightly).
- [ ] `index_memberships`:
  - `PENDING → INDEXED` per chunk, in each engine;
  - when both engines confirm all chunks of a version, the version becomes `VALIDATING_INDEX` → `PUBLISHED`, and the previous version becomes `SUPERSEDED`.
- [ ] Validation records one `index_validations` row per check:
  - counts (memberships vs Qdrant vs OpenSearch);
  - missing, duplicate and orphaned records;
  - dense, lexical and hybrid smoke searches.
- [ ] Publish and rollback happen in one transaction (the new generation becomes `PUBLISHED`, the old one `RETIRED`), each with an audit event.
- [ ] Endpoints:
  - `index-generations/` (list, create = build);
  - `{id}/`, `{id}/validate/`, `{id}/rollback/`.
- [ ] First publish: `pipeline-versions/{id}/publish-initial/` (Phase 3) now also publishes the validated generation.

### Console
- [ ] `/indexes`:
  - generations with status, chunk counts per engine and validation results;
  - the live generation highlighted;
  - **Build** (`indexes.build`);
  - **Roll back** (`releases.approve`, with `ConfirmDialog`).

### Tests (integration, against the real local Qdrant and OpenSearch)
- [ ] Upserting the same version twice leaves the counts unchanged.
- [ ] **Access:** a document shared only with `finance` returns zero hits in **both** engines for a user whose scope is `{general}`, and does return hits for `{finance}`.
- [ ] Changing a document's groups updates `access_groups` in both engines (`index.acl`).
- [ ] Deleting a document removes it from both engines, and its memberships become `REMOVED`.
- [ ] If one engine is missing a chunk, validation fails and publishing is refused.
- [ ] `reconcile` finds and repairs a chunk deleted by hand from one engine.

## Done when

- [ ] Every fixture document ends as `PUBLISHED`, and the first generation is live.
- [ ] Direct queries to Qdrant and OpenSearch, with a scope that should see nothing, return nothing.
- [ ] Rollback to the previous generation works, and is visible in the console.

## Risks and tips

- **Never let one engine run ahead of the other.** The query path reads the live names from PostgreSQL. Aliases are for operators only.
- Keep chunk text out of the Qdrant payload. Text comes from PostgreSQL by chunk ID, which keeps Qdrant's memory use small.
