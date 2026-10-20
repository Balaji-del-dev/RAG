# Phase 5: Processing pipeline

## Goal

The Celery worker turns every uploaded version into clean, structured, canonical chunks with embeddings, all on the CPU:

1. read the original;
2. parse;
3. OCR if needed;
4. clean;
5. rebuild the structure;
6. chunk;
7. check the chunks;
8. save them;
9. embed them.

Every step is recorded, retryable and idempotent. The last step queues the document for indexing.

## Before you start

- Phase 4 is done: uploads create jobs that reach the `ingest` queue.
- The Docling, OCR and embedding models are in `~/rag-data/models/` (Phase 0).

## Tasks

### Backend (`processing`)
- [ ] Models: all 6 tables of 4.3.
- [ ] `processing.run_job(job_id)` replaces the Phase 4 stub. For each enabled step, in `step_order`, it:
  - writes a `processing_step_runs` row (`RUNNING` → `SUCCEEDED` / `FAILED` / `SKIPPED`);
  - records the input and output summaries and the duration;
  - updates `document_versions.status` (`PROCESSING`).
- [ ] Retries:
  - steps that already succeeded are skipped;
  - transient errors are retried up to 3 times with backoff;
  - content errors fail at once, and the message is kept;
  - `jobs/{id}/retry/` and `jobs/{id}/cancel/` endpoints.
- [ ] The steps ([01-backend.md §2.5](../01-backend.md#25-processing)):
  - [ ] **1 Read:** stream from MinIO and re-check the SHA-256.
  - [ ] **2 Parse:** Docling for PDF, DOCX, PPTX, XLSX, HTML and MD; PyMuPDF for PDF text and pages; plain readers for TXT, CSV, JSON and XML. Save the Docling JSON to `rag-artifacts` and record it in `extracted_artifacts`.
  - [ ] **3 OCR fallback:** only for pages with fewer than about 50 characters: Tesseract `eng+tam+hin`, then EasyOCR (`gpu=False`) if confidence is low. Save the OCR text as an artifact.
  - [ ] **4 Normalize:** NFKC, whitespace, line-break hyphenation.
  - [ ] **5 Rebuild structure:** `document_elements` with type, order, page and `section_path`.
  - [ ] **6 Enrich:** `enrich.none` in the baseline.
  - [ ] **7 Chunk:** structure-aware, ≤ ~400 tokens, ~50 tokens of overlap. Keep tables whole, or split them by rows with the header repeated. Record parent links and `chunk_relationships`.
  - [ ] **8 Quality checks:** empty, oversized, duplicate `content_hash`, broken tables. Record the counts in the step's output summary.
  - [ ] **9 Save chunks:** one transaction, deterministic `uuid5` chunk IDs, `ON CONFLICT DO NOTHING`.
  - [ ] **10 Embed:** `core/clients/embedder.py` with the `passage: ` prefix, batches of 16–32 and normalized vectors. Write `embedding_records`, and the `index.upsert` outbox row in the same final transaction. The version becomes `INDEXING`.
- [ ] Worker settings: `--concurrency=1 --max-tasks-per-child=20`; soft time limit 30 minutes, hard 35 minutes; `torch.set_num_threads(4)`.

### Console
- [ ] `JobTimeline` on `/documents/:id`: each step with its status, duration and error.
- [ ] **Retry** and **Cancel** buttons (`jobs.retry`).
- [ ] Polling while the document is `PROCESSING`.

### Tests
- [ ] Each of the 10 fixture formats produces elements and chunks with page numbers and section paths.
- [ ] A scanned-page PDF fixture triggers OCR and produces text.
- [ ] **Idempotency:** running the same job twice gives exactly the same chunk IDs, with no duplicate rows.
- [ ] A failure in step 7 keeps steps 1–6 as `SUCCEEDED`. A retry starts at step 7.
- [ ] Chunk sizes stay ≤ 400 tokens (measured with the embedding model's tokenizer).
- [ ] The final transaction writes `embedding_records` and the `index.upsert` outbox row together.

## Done when

- [ ] All 10 formats end with chunks and embeddings, and the version status is `INDEXING`.
- [ ] Re-running every job creates zero new rows.
- [ ] Measure and record, for comparison in Phase 9:
  - the time and peak memory for a 50-page text PDF;
  - the same for a 10-page scanned PDF.

## Risks and tips

- **Memory:** Docling and EasyOCR are the biggest users. Parse long PDFs in page batches, and do not ingest while you are testing chat.
- **OCR is slow on the CPU.** Use it only when a page really lacks text.
- Keep the chunker's settings in the pipeline step config. Then a change is a new pipeline version that evaluation can measure, not a code edit.
