# Phase 8: Evaluation & release

## Goal

Quality is measured, not guessed. A golden dataset is run against a candidate pipeline version and index generation, and the results are compared with the live baseline. A release approver who is **not** the author approves, and the release is published in one transaction.

Admins can read the full audit log.

This phase reaches **Milestone M4: measured release**.

## Before you start

- Phase 7 is done: the orchestrator answers questions.
- 30–50 real questions and their expected sources, written with the people who own the documents.

## Tasks

### Backend (`evaluation`)
- [ ] Models: `evaluation_datasets`, `evaluation_cases`, `evaluation_runs`, `evaluation_results`. `audit_events` exists already, from Phase 1.
- [ ] Datasets:
  - versioned;
  - frozen once a run uses them;
  - import from CSV or JSON;
  - "create from reviewed failure cases" makes a new version.
- [ ] The service account `svc-evaluation`:
  - created by a data migration;
  - no password; cannot sign in;
  - Evaluator role; member of every access group.
- [ ] `evaluation.run_evaluation(run_id)` on the `evaluation` queue. For each case it runs the orchestrator, not streamed, on the candidate pipeline version and generation, then computes:
  - **retrieval metrics**, in our own code, from `expected_sources`: hit@5, recall@5, MRR;
  - **answer metrics**, from DeepEval with the local `qwen2.5:3b` judge through Ollama: faithfulness, answer relevancy, contextual precision, contextual recall;
  - **behaviour checks:** `NO_ANSWER` cases must abstain, and `ACCESS` cases must not cite forbidden documents.
- [ ] Results:
  - write `evaluation_results` (one row per case per metric);
  - write `summary_json` with the means and the baseline values;
  - save the report to `rag-exports/evaluations/<run_id>/`.
- [ ] **Gates** (in settings):
  - minimum value per metric;
  - maximum allowed drop against the baseline;
  - `ACCESS` cases must be 100 %.
- [ ] Each run ends `PASSED`, `FAILED` or `ERROR`.
- [ ] **Judge calibration:** 20–30 cases labelled by a person. Record how often the judge agrees, and keep the judge model fixed across runs you compare.
- [ ] `POST eval/runs/{id}/approve/` checks all of these:
  - the caller has `releases.approve`;
  - the run is `PASSED`;
  - the caller is not `pipeline_versions.created_by`;
  - the generation is validated.

  Then **one transaction**:
  - sets `approved_by`;
  - publishes the version (`published_by`, `published_at`) and the generation;
  - retires the old ones;
  - writes the audit event.
- [ ] Failure review:
  - `failure-cases/` moves cases `OPEN → IN_REVIEW → RESOLVED` or `WONT_FIX`;
  - a resolved case can be copied into the dataset.
- [ ] `GET audit-events/` (`audit.read`), with filters.

### Console
- [ ] `/evaluation/datasets`: datasets, versions, a cases editor and import.
- [ ] `/evaluation`:
  - runs, with status and gate result;
  - **Start run**: choose a dataset, pipeline version and generation.
- [ ] `/evaluation/runs/:id`:
  - a metrics table (candidate vs baseline, with simple CSS bars);
  - failed cases with their answers and sources;
  - gate details;
  - **Approve**, which shows *why* it is disabled when a rule blocks it.
- [ ] `/evaluation/failures`: the review workflow.
- [ ] `/admin/audit`: the audit log, with filters.

### Tests
- [ ] **Four-eyes:** the author of a version gets `409` on approve; a different Release approver succeeds.
- [ ] A run that fails a gate cannot be approved.
- [ ] Approval publishes the version and the generation together. If either step fails, neither changes.
- [ ] The metric code: hit@k, recall@k and MRR on a tiny hand-made case.
- [ ] `ACCESS` cases fail the run if a forbidden document is cited.

## Done when

- [ ] A baseline run exists for the live pipeline.
- [ ] A candidate version with one changed setting has been:
  - evaluated;
  - compared with the baseline in the console;
  - approved by a different person;
  - published.
- [ ] The audit log shows the whole release: the draft edit, the run, the approval and the publish.

## Risks and tips

- **Evaluation is slow on the CPU.** Each case makes several LLM calls, so a 50-case run can take hours. Run it overnight, with chat stopped.
- Small judges are noisy. Treat a difference of a few points as noise until calibration says otherwise.
