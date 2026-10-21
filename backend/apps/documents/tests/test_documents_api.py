import io
import zipfile

import pymupdf
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import AccessGroup, DocumentAccessGrant
from apps.core.models import OutboxEvent
from apps.documents.models import Document, DocumentVersion
from apps.evaluation.models import AuditEvent
from apps.processing.models import ProcessingJob
from apps.registry.models import PipelineVersion


@pytest.fixture(autouse=True)
def live_pipeline(db):
    PipelineVersion.objects.filter(pipeline__name="default", version_number=1).update(status="PUBLISHED")


@pytest.fixture
def minio(monkeypatch):
    """A fake MinIO: remembers what was stored."""
    from apps.core.clients import storage

    stored: dict[str, bytes] = {}

    def put_file(bucket, key, path, content_type, metadata=None):
        with open(path, "rb") as handle:
            stored[f"{bucket}/{key}"] = handle.read()
        return "version-1"

    def stream(bucket, key, version_id=None, chunk_size=65536):
        yield stored[f"{bucket}/{key}"]

    monkeypatch.setattr(storage, "put_file", put_file)
    monkeypatch.setattr(storage, "stream", stream)
    return stored


def general_id():
    return str(AccessGroup.objects.get(name="general").pk)


def upload(api, name, content, groups=None, content_type="application/octet-stream"):
    return api.post(
        "/api/v1/documents/",
        {
            "file": SimpleUploadedFile(name, content, content_type=content_type),
            "access_group_ids": [general_id()] if groups is None else groups,
        },
        format="multipart",
    )


def pdf_bytes(text="Hello PDF", encrypt=False):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    buffer = io.BytesIO()
    if encrypt:
        doc.save(buffer, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    else:
        doc.save(buffer)
    return buffer.getvalue()


def office_bytes(main_part="word/document.xml", payload=b"<w:document/>"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(main_part, payload)
    return buffer.getvalue()


@pytest.fixture
def manager(signed_in):
    return signed_in("Knowledge manager")


def test_upload_writes_minio_and_every_row_in_one_go(manager, minio):
    api, user = manager
    response = upload(api, "notes.txt", b"Hello world from a text file.")
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["duplicate"] is False
    document = Document.objects.get(pk=body["document"]["id"])
    version = document.current_version
    assert version.status == "QUEUED" and version.version_number == 1 and version.storage_version_id == "version-1"
    assert version.storage_object_key == f"documents/{document.pk}/v1/{version.content_sha256}.txt"
    assert minio[f"rag-originals/{version.storage_object_key}"] == b"Hello world from a text file."
    assert [g["name"] for g in body["document"]["access_groups"]] == ["general"]
    job = ProcessingJob.objects.get(document_version=version)
    assert job.status == "QUEUED" and job.pipeline_version.version_number == 1
    assert OutboxEvent.objects.filter(event_type="job.dispatch", aggregate_id=job.pk).exists()
    assert AuditEvent.objects.filter(event_type="document.uploaded", actor_user=user).exists()


@pytest.mark.parametrize(
    ("name", "content", "code"),
    [
        ("tool.exe", b"MZ\x90\x00", "unsupported_file_type"),
        ("report.pdf", b"MZ\x90\x00\x03\x00\x00\x00\x04\x00", "unsupported_file_type"),
        ("empty.txt", b"", "invalid_file"),
        ("latin1.txt", "café".encode("latin-1"), "invalid_file"),
        ("data.json", b"{not json", "invalid_file"),
        ("fake.docx", office_bytes(main_part="xl/workbook.xml"), "invalid_file"),
        ("locked.pdf", pdf_bytes(encrypt=True), "invalid_file"),
        ("bomb.docx", office_bytes(payload=b"0" * 50_000_000), "invalid_file"),
    ],
    ids=["exe", "exe-named-pdf", "empty", "not-utf8", "bad-json", "docx-without-word-part", "encrypted-pdf", "zip-bomb"],
)
def test_bad_files_are_refused(manager, minio, name, content, code):
    api, _ = manager
    response = upload(api, name, content)
    assert response.status_code in (400, 415), response.json()
    assert response.json()["error"]["code"] == code
    assert not Document.objects.exists() and not minio


def test_too_large_is_413(manager, minio, settings):
    settings.UPLOAD_MAX_BYTES = 10
    api, _ = manager
    response = upload(api, "big.txt", b"x" * 100)
    assert response.status_code == 413 and response.json()["error"]["code"] == "file_too_large"


def test_valid_pdf_and_docx_are_accepted(manager, minio):
    api, _ = manager
    assert upload(api, "a.pdf", pdf_bytes()).status_code == 201
    assert upload(api, "b.docx", office_bytes()).status_code == 201


def test_the_same_bytes_return_the_existing_document(manager, minio):
    api, _ = manager
    first = upload(api, "a.txt", b"same bytes here").json()
    second = upload(api, "copy.txt", b"same bytes here")
    assert second.status_code == 200 and second.json()["duplicate"] is True
    assert second.json()["document"]["id"] == first["document"]["id"]
    assert Document.objects.count() == 1


def test_groups_are_required_and_must_be_your_own(manager, minio):
    api, _ = manager
    assert upload(api, "a.txt", b"text", groups=[]).json()["error"]["details"]["access_group_ids"]
    finance = AccessGroup.objects.create(name="finance")
    response = upload(api, "a.txt", b"text", groups=[str(finance.pk)])
    assert response.status_code == 400 and "access_group_ids" in response.json()["error"]["details"]


def test_users_cannot_upload(signed_in, minio):
    api, _ = signed_in("User")
    assert upload(api, "a.txt", b"text").status_code == 403


def test_no_live_pipeline_means_no_uploads(manager, minio):
    PipelineVersion.objects.update(status="RETIRED")  # published versions may retire, never go back to draft
    api, _ = manager
    response = upload(api, "a.txt", b"text")
    assert response.status_code == 409 and response.json()["error"]["code"] == "no_live_pipeline"


def test_documents_outside_my_groups_are_404(signed_in, minio):
    owner, _ = signed_in("Knowledge manager", groups=["general", "finance"])
    finance = AccessGroup.objects.get(name="finance")
    doc_id = upload(owner, "secret.txt", b"finance only", groups=[str(finance.pk)]).json()["document"]["id"]
    reader, _ = signed_in("User", groups=["general"])
    assert reader.get("/api/v1/documents/").json()["count"] == 0
    assert reader.get(f"/api/v1/documents/{doc_id}/").status_code == 404
    assert reader.get(f"/api/v1/documents/{doc_id}/download/").status_code == 404
    insider, _ = signed_in("User", groups=["finance"])
    assert insider.get(f"/api/v1/documents/{doc_id}/").status_code == 200


def test_download_streams_the_original(manager, minio):
    api, _ = manager
    doc_id = upload(api, "notes.txt", b"download me").json()["document"]["id"]
    response = api.get(f"/api/v1/documents/{doc_id}/download/")
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"download me"
    assert "notes.txt" in response["Content-Disposition"]


def test_new_version_must_have_the_same_type(manager, minio):
    api, _ = manager
    doc_id = upload(api, "notes.txt", b"version one").json()["document"]["id"]
    v2 = api.post(
        f"/api/v1/documents/{doc_id}/versions/", {"file": SimpleUploadedFile("notes.txt", b"version two")}, format="multipart"
    )
    assert v2.status_code == 201 and [v["version_number"] for v in v2.json()["versions"]] == [2, 1]
    wrong = api.post(f"/api/v1/documents/{doc_id}/versions/", {"file": SimpleUploadedFile("n.md", b"# md")}, format="multipart")
    assert wrong.status_code == 400


def test_delete_hides_the_document_and_queues_index_removal(manager, minio):
    api, _ = manager
    doc_id = upload(api, "notes.txt", b"delete me").json()["document"]["id"]
    assert api.delete(f"/api/v1/documents/{doc_id}/").status_code == 204
    assert api.get(f"/api/v1/documents/{doc_id}/").status_code == 404
    assert DocumentVersion.objects.get(document_id=doc_id).status == "DELETED"
    assert OutboxEvent.objects.filter(event_type="index.delete").count() == 1
    assert ProcessingJob.objects.get(document_version__document_id=doc_id).status == "CANCELLED"


def test_changing_access_rewrites_grants_and_queues_index_acl(signed_in, minio):
    api, _ = signed_in("Knowledge manager", groups=["general", "hr"])
    doc_id = upload(api, "notes.txt", b"share me").json()["document"]["id"]
    hr = AccessGroup.objects.get(name="hr")
    response = api.put(f"/api/v1/documents/{doc_id}/access/", {"access_group_ids": [str(hr.pk)]}, format="json")
    assert response.status_code == 200
    assert list(DocumentAccessGrant.objects.filter(document_id=doc_id).values_list("access_group__name", flat=True)) == ["hr"]
    assert OutboxEvent.objects.filter(event_type="index.acl", aggregate_id=doc_id).exists()


def test_a_failed_transaction_leaves_no_rows(manager, minio, monkeypatch):
    from apps.documents import services

    def broken(*args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(services, "_queue_job", broken)
    api, _ = manager
    with pytest.raises(RuntimeError):
        upload(api, "notes.txt", b"atomic please")
    assert not Document.objects.exists() and not ProcessingJob.objects.exists() and not OutboxEvent.objects.exists()
