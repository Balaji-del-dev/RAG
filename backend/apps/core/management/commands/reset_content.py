"""Remove all content and keep the set-up: start again with an empty library.

    python manage.py reset_content          # dry run: shows what would be removed
    python manage.py reset_content --yes    # removes it (take a backup first: python manage.py backup)

Removed: documents and their files, processing jobs and chunks, index generations (and their Qdrant collections and
OpenSearch indexes), chat history and feedback, evaluation datasets and runs, outbox events.
Kept: users, roles, access groups, sessions, pipelines and their settings, and the audit log (append-only).
"""

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.core import audit
from apps.core.clients import search_index, storage, vector_store

CONTENT = [
    "retrieval.FailureCase", "retrieval.UserFeedback", "retrieval.AnswerRecord", "retrieval.RetrievalResult",
    "retrieval.RetrievalRun",
    "evaluation.EvaluationResult", "evaluation.EvaluationRun", "evaluation.EvaluationCase", "evaluation.EvaluationDataset",
    "indexing.IndexValidation", "indexing.IndexMembership", "indexing.IndexBuildJob", "indexing.IndexGeneration",
    "processing.EmbeddingRecord", "processing.ChunkRelationship", "processing.Chunk", "processing.DocumentElement",
    "processing.ProcessingStepRun", "processing.ProcessingJob",
    "accounts.DocumentAccessGrant",
    "documents.ExtractedArtifact", "documents.StorageObject", "documents.DocumentMetadata", "documents.DocumentVersion",
    "documents.Document",
    "core.OutboxEvent",
]  # fmt: skip


def content_models() -> list:
    return [apps.get_model(label) for label in CONTENT]


def outside_references(models: list) -> list[str]:
    """Kept tables with a foreign key into the content tables (removing would break them)."""
    inside = set(models)
    problems = []
    for model in apps.get_models():
        if model in inside:
            continue
        for field in model._meta.concrete_fields:
            if field.is_relation and field.related_model in inside:
                problems.append(f"{model._meta.db_table}.{field.column} -> {field.related_model._meta.db_table}")
    return problems


class Command(BaseCommand):
    help = "Remove documents, chunks, indexes, chat history and evaluation data; keep users, roles and pipelines."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Really remove it (without this: a dry run).")

    def handle(self, *args, yes: bool, **options):
        models = content_models()
        problems = outside_references(models)
        if problems:
            raise CommandError("Kept tables still point at content tables: " + "; ".join(problems))
        counts = {model._meta.db_table: model.objects.count() for model in models}
        generation_model = apps.get_model("indexing.IndexGeneration")
        generations = list(generation_model.objects.values_list("qdrant_collection", "opensearch_index"))
        for table, n in counts.items():
            self.stdout.write(f"  {table:28} {n:>7} rows")
        self.stdout.write(f"  search indexes: {len(generations)} Qdrant collection(s) and OpenSearch index(es)")
        self.stdout.write(f"  MinIO: every file in {settings.S3_BUCKET_ORIGINALS} and {settings.S3_BUCKET_ARTIFACTS}")
        if not yes:
            self.stdout.write(self.style.WARNING("Dry run: nothing removed. Add --yes to remove it."))
            return

        with transaction.atomic():
            tables = ", ".join(connection.ops.quote_name(m._meta.db_table) for m in models)
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # run deferred FK checks first, or TRUNCATE refuses
                cursor.execute(f"TRUNCATE {tables}")  # no CASCADE: fails if any other table still refers to these
            audit.record("content.reset", actor="reset_content", entity_type="system", details={"rows": counts})
        for collection, index in generations:
            vector_store.drop(collection)
            search_index.drop(index)
        files = sum(storage.remove_prefix(bucket, "") for bucket in (settings.S3_BUCKET_ORIGINALS, settings.S3_BUCKET_ARTIFACTS))
        removed = f"Removed {sum(counts.values())} rows, {len(generations)} index generation(s), {files} file(s)."
        self.stdout.write(self.style.SUCCESS(removed))
