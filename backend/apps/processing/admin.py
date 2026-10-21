from apps.accounts.admin_site import register

from .models import Chunk, ChunkRelationship, DocumentElement, EmbeddingRecord, ProcessingJob, ProcessingStepRun

# Written by the Celery pipeline; chunks are the canonical copy behind both search indexes.
INDEXES_NOT_TOUCHED = (
    "Saved in PostgreSQL only: Qdrant and OpenSearch keep their copy until the document is re-processed. "
    "The nightly reconcile job removes index entries whose chunk was deleted."
)

register(ProcessingJob, ProcessingStepRun, DocumentElement, Chunk, ChunkRelationship, EmbeddingRecord,
         save_warning=INDEXES_NOT_TOUCHED)  # fmt: skip
