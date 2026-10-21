"""The real ingestion pipeline (Docling, Tesseract, the e5 tokenizer and embedder) on small files; MinIO is faked."""

import hashlib
import io

import pymupdf
import pytest
from PIL import Image, ImageDraw, ImageFont

from apps.core.models import OutboxEvent
from apps.documents.models import Document, DocumentVersion
from apps.processing import runner
from apps.processing.models import Chunk, ChunkRelationship, DocumentElement, EmbeddingRecord, ProcessingJob
from apps.registry.models import PipelineVersion

pytestmark = pytest.mark.slow


@pytest.fixture
def v1(db):
    PipelineVersion.objects.filter(version_number=1).update(status="PUBLISHED")
    return PipelineVersion.objects.get(version_number=1)


@pytest.fixture
def minio(monkeypatch):
    from apps.core.clients import storage

    objects: dict[str, bytes] = {}

    def download_to(bucket, key, path, version_id=None):
        with open(path, "wb") as handle:
            handle.write(objects[f"{bucket}/{key}"])

    monkeypatch.setattr(storage, "download_to", download_to)
    monkeypatch.setattr(
        storage, "put_bytes", lambda bucket, key, data, content_type="": objects.__setitem__(f"{bucket}/{key}", data)
    )
    monkeypatch.setattr(storage, "read_bytes", lambda bucket, key, version_id=None: objects[f"{bucket}/{key}"])
    return objects


def make_job(make_user, minio, v1, filename: str, content: bytes, sha=None) -> ProcessingJob:
    user = make_user("Knowledge manager")
    ext = filename.rsplit(".", 1)[1]
    document = Document.objects.create(
        filename=filename, file_extension=ext, mime_type="application/octet-stream", created_by=user
    )
    key = f"documents/{document.pk}/v1/x.{ext}"
    minio[f"rag-originals/{key}"] = content
    version = DocumentVersion.objects.create(
        document=document, version_number=1, content_sha256=sha or hashlib.sha256(content).hexdigest(), file_size=len(content),
        storage_bucket="rag-originals", storage_object_key=key, status="QUEUED",
    )  # fmt: skip
    document.current_version = version
    document.save()
    return ProcessingJob.objects.create(document_version=version, pipeline_version=v1)


MARKDOWN = b"""# Leave policy

## Annual leave
Every employee gets 24 days of annual leave per year. Unused days carry over up to 5 days.

## Sick leave
Sick leave needs a doctor's note after 3 days. Sick leave is paid in full for 10 days.
"""


def test_markdown_becomes_sectioned_chunks_with_embeddings(make_user, minio, v1):
    job = make_job(make_user, minio, v1, "policy.md", MARKDOWN)
    assert runner.run(str(job.pk)) == "SUCCEEDED"
    job.refresh_from_db()
    version = job.document_version
    version.refresh_from_db()
    assert version.status == "INDEXING"
    steps = list(job.step_runs.order_by("input_summary__step_order").values_list("step_name", "status"))
    assert len(steps) == 10 and all(status in ("SUCCEEDED", "SKIPPED") for _, status in steps)
    chunks = list(Chunk.objects.filter(document_version=version).order_by("chunk_index"))
    assert {c.section_path for c in chunks} == {"Leave policy > Annual leave", "Leave policy > Sick leave"}
    assert all(c.token_count <= 400 for c in chunks)
    assert EmbeddingRecord.objects.filter(chunk__in=chunks, vector_dimension=384).count() == len(chunks)
    assert ChunkRelationship.objects.filter(relationship_type="NEXT").count() == len(chunks) - 1
    types = list(
        DocumentElement.objects.filter(document_version=version, element_type__in=["TITLE", "HEADING"])
        .order_by("element_order")
        .values_list("element_type", flat=True)
    )
    assert types == ["TITLE", "HEADING", "HEADING"]
    event = OutboxEvent.objects.get(event_type="index.upsert")
    assert event.payload == {"document_version_id": str(version.pk), "pipeline_version_id": str(v1.pk)}


def test_running_a_job_twice_gives_the_same_chunks(make_user, minio, v1):
    job = make_job(make_user, minio, v1, "policy.md", MARKDOWN)
    runner.run(str(job.pk))
    first = set(Chunk.objects.values_list("id", flat=True))
    ProcessingJob.objects.filter(pk=job.pk).update(status="QUEUED")
    assert runner.run(str(job.pk)) == "SUCCEEDED"
    assert set(Chunk.objects.values_list("id", flat=True)) == first
    assert EmbeddingRecord.objects.count() == len(first)
    embed_runs = job.step_runs.filter(step_name="embed.sentence_transformers").order_by("input_summary__attempt")
    assert [r.status for r in embed_runs] == ["SUCCEEDED", "SKIPPED"]  # the saved vectors are reused


def test_csv_becomes_a_table_chunk(make_user, minio, v1):
    job = make_job(make_user, minio, v1, "prices.csv", b"item,price\napple,3\npear,4\n")
    assert runner.run(str(job.pk)) == "SUCCEEDED"
    chunk = Chunk.objects.get()
    assert chunk.metadata_json["kind"] == "table" and "| apple | 3 |" in chunk.text_content


def pdf_with_text(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Quarterly report", fontsize=18)
    page.insert_textbox(pymupdf.Rect(72, 110, 520, 700), text, fontsize=11)
    return doc.tobytes()


def test_pdf_is_parsed_with_page_numbers(make_user, minio, v1):
    job = make_job(make_user, minio, v1, "report.pdf", pdf_with_text("Revenue grew by 12 percent in the third quarter. " * 5))
    assert runner.run(str(job.pk)) == "SUCCEEDED", job.step_runs.values_list("step_name", "error_message")
    chunk = Chunk.objects.first()
    assert chunk.page_start == 1 and "Revenue grew by 12 percent" in chunk.text_content


def scanned_pdf(text: str) -> bytes:
    image = Image.new("RGB", (1700, 600), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 48)
    except OSError:
        font = ImageFont.load_default(size=48)
    draw.text((60, 200), text, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    doc = pymupdf.open()
    page = doc.new_page(width=850, height=300)
    page.insert_image(page.rect, stream=buffer.getvalue())
    return doc.tobytes()


def test_scanned_pages_are_ocred(make_user, minio, v1):
    job = make_job(make_user, minio, v1, "scan.pdf", scanned_pdf("The invoice total is 4500 rupees"))
    assert runner.run(str(job.pk)) == "SUCCEEDED", job.step_runs.values_list("step_name", "error_message")
    ocr = job.step_runs.get(step_name="ocr.tesseract")
    assert ocr.output_summary["pages_ocred"] == 1
    assert "4500" in Chunk.objects.get().text_content


def test_a_changed_file_fails_with_a_clear_message(make_user, minio, v1):
    job = make_job(make_user, minio, v1, "notes.txt", b"some text", sha="0" * 64)
    assert runner.run(str(job.pk)) == "FAILED"
    job.refresh_from_db()
    assert "SHA-256" in job.error_message
    assert job.document_version.status == "FAILED" and job.document_version.document.lifecycle_status == "FAILED"
    assert job.step_runs.get().status == "FAILED"


def test_retry_and_cancel_follow_the_rules(signed_in, make_user, minio, v1):
    job = make_job(make_user, minio, v1, "notes.txt", b"some text", sha="0" * 64)
    runner.run(str(job.pk))
    api, _ = signed_in("Knowledge manager")
    detail = api.get(f"/api/v1/jobs/{job.pk}/")
    assert detail.status_code == 404  # another manager's document in the same group is visible…
    job.document_version.document.access_grants.create(
        access_group_id=__import__("apps.accounts.models", fromlist=["AccessGroup"]).AccessGroup.objects.get(name="general").pk
    )
    detail = api.get(f"/api/v1/jobs/{job.pk}/").json()
    assert detail["status"] == "FAILED" and detail["steps"][0]["status"] == "FAILED"
    assert api.post(f"/api/v1/jobs/{job.pk}/cancel/").status_code == 409
    assert api.post(f"/api/v1/jobs/{job.pk}/retry/").json()["status"] == "QUEUED"
    assert OutboxEvent.objects.filter(event_type="job.dispatch", aggregate_id=job.pk).exists()
    assert api.post(f"/api/v1/jobs/{job.pk}/cancel/").json()["status"] == "CANCELLED"
    viewer, _ = signed_in("User")
    assert viewer.get("/api/v1/jobs/").status_code == 403
