# Phase 3: Pipeline registry

## Goal

Pipeline versions, components, models and retrieval and generation settings are stored, validated and versioned. The default pipeline version 1 exists as a draft, with the baseline steps.

Pipeline engineers can clone a version and edit a draft. They can never change a published version.

## Before you start

- Phase 2 is done: roles and permissions work.

## Tasks

### Backend (`registry`)
- [ ] Models for all 7 tables in 4.1, including `pipeline_versions.created_by`.
- [ ] Partial unique indexes:
  - one active pipeline definition;
  - one `PUBLISHED` version per pipeline.
- [ ] The component allow-list in code (`implementation_key` → class, [01-backend.md §2.3](../01-backend.md#23-registry)):
  - each class declares a pydantic config model;
  - `config_schema` stores its JSON schema.
- [ ] Services:
  - `clone_version` (sets `created_by`);
  - `update_draft`;
  - `replace_steps`.
- [ ] Every step config is validated against its component's pydantic model when saved.
- [ ] A change to a `PUBLISHED` version → `409 version_published`.
- [ ] Endpoints:
  - `pipelines/`, `pipeline-versions/{id}/`, `…/clone/`, `…/steps/`;
  - `components/`, `models/`;
  - `retrieval-definitions/`, `generation-definitions/`;
  - `…/publish-initial/` (first version only, `releases.approve`).
- [ ] Data migration `registry 0002`:
  - components;
  - 4 model records;
  - the `baseline` retrieval settings;
  - the `grounded-v1` generation settings;
  - `default` pipeline version 1 as `DRAFT`, with steps 1–10 ([03-database.md §8](../03-database.md#8-seed-data)).
- [ ] Audit events for each draft change, clone and publish.

### Console
- [ ] `/pipelines`: the list of pipelines and versions, with status badges.
- [ ] `/pipelines/:id/versions/:v`:
  - steps in order, with component, enabled flag and settings;
  - models; retrieval and generation settings.
- [ ] A **Clone to new draft** button.
- [ ] In a draft:
  - a `JsonEditor` per step;
  - the server's validation errors shown next to the field;
  - steps reordered with up and down buttons.
- [ ] Read-only view for `pipelines.view` users and for published versions.

### Tests
- [ ] A step config that does not match its schema gives a `400` with field errors.
- [ ] An unknown `implementation_key` can never be saved.
- [ ] Editing a published version gives `409`.
- [ ] A clone records `created_by`.
- [ ] `publish-initial` works only while no version is published, and only for `releases.approve`.

## Done when

- [ ] The seeded `default` v1 draft loads in the console, with all 10 steps.
- [ ] A Pipeline engineer can clone a version, edit a setting and see validation errors. A User cannot open the page, and the API returns `403`.

## Risks and tips

- Keep the allow-list in code and review it in pull requests. The database only chooses **which** allowed component runs, never **what code** runs.
- `publish-initial` can be used from Phase 6 on, once a validated index generation exists. Phase 8 replaces it with evaluated releases.
