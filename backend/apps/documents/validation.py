"""Upload checks, in order: extension → sniffed MIME → size → content → SHA-256. Never trust the browser."""

import hashlib
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass

import magic
from django.conf import settings
from rest_framework import exceptions, status


class FileTooLarge(exceptions.APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "The file is too large."
    default_code = "file_too_large"


class UnsupportedFileType(exceptions.APIException):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    default_detail = "This file type is not supported."
    default_code = "unsupported_file_type"


class InvalidFile(exceptions.APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The file could not be read."
    default_code = "invalid_file"


ZIP_FAMILY = {"application/zip", "application/x-zip-compressed", "application/octet-stream"}
TEXT_FAMILY = {"text/plain", "application/octet-stream", "inode/x-empty"}

# extension -> (MIME types libmagic may report, MIME type we store)
FORMATS: dict[str, tuple[set[str], str]] = {
    "pdf": ({"application/pdf"}, "application/pdf"),
    "docx": ({"application/vnd.openxmlformats-officedocument.wordprocessingml.document"} | ZIP_FAMILY,
             "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "xlsx": ({"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"} | ZIP_FAMILY,
             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "pptx": ({"application/vnd.openxmlformats-officedocument.presentationml.presentation"} | ZIP_FAMILY,
             "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    "txt": (TEXT_FAMILY, "text/plain"),
    "md": (TEXT_FAMILY | {"text/markdown", "text/x-markdown"}, "text/markdown"),
    "csv": (TEXT_FAMILY | {"text/csv", "application/csv"}, "text/csv"),
    "json": (TEXT_FAMILY | {"application/json"}, "application/json"),
    "xml": (TEXT_FAMILY | {"text/xml", "application/xml"}, "application/xml"),
    "html": (TEXT_FAMILY | {"text/html"}, "text/html"),
    "htm": (TEXT_FAMILY | {"text/html"}, "text/html"),
}  # fmt: skip

# The main part every Office Open XML file of that type must contain.
OFFICE_MAIN_PART = {"docx": "word/document.xml", "xlsx": "xl/workbook.xml", "pptx": "ppt/presentation.xml"}

MAX_ZIP_ENTRIES = 10_000
MAX_ZIP_UNCOMPRESSED = 300 * 1024 * 1024
MAX_ZIP_RATIO = 100
MAX_PDF_PAGES = 2000


@dataclass
class CheckedFile:
    path: str  # a temporary copy; the caller deletes it
    filename: str
    extension: str
    mime_type: str
    size: int
    sha256: str


def safe_filename(name: str) -> str:
    """Display name only: no folders, no control characters, at most 255 characters."""
    name = os.path.basename(name.replace("\\", "/")).strip()
    name = "".join(ch for ch in name if ch.isprintable())
    return (name or "unnamed")[:255]


def extension_of(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _copy_and_hash(uploaded) -> tuple[str, int, str]:
    digest = hashlib.sha256()
    size = 0
    handle, path = tempfile.mkstemp(prefix="rag-upload-")
    with os.fdopen(handle, "wb") as out:
        for chunk in uploaded.chunks():
            size += len(chunk)
            if size > settings.UPLOAD_MAX_BYTES:
                out.close()
                os.unlink(path)
                raise FileTooLarge(f"The file is larger than {settings.UPLOAD_MAX_BYTES // (1024 * 1024)} MB.")
            digest.update(chunk)
            out.write(chunk)
    return path, size, digest.hexdigest()


def _check_office(path: str, extension: str) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ZIP_ENTRIES:
                raise InvalidFile("The file has too many parts to be a normal Office document.")
            total = sum(entry.file_size for entry in entries)
            packed = sum(entry.compress_size for entry in entries) or 1
            if total > MAX_ZIP_UNCOMPRESSED or total / packed > MAX_ZIP_RATIO:
                raise InvalidFile("The file expands to an unsafe size (possible zip bomb).")
            if OFFICE_MAIN_PART[extension] not in archive.namelist():
                raise InvalidFile(f"This is not a real .{extension} file.")
    except zipfile.BadZipFile:
        raise InvalidFile(f"This is not a real .{extension} file.")


def _check_pdf(path: str) -> None:
    import pymupdf

    try:
        with pymupdf.open(path) as pdf:
            if pdf.needs_pass or pdf.is_encrypted:
                raise InvalidFile("Password-protected PDFs can't be processed. Upload an unprotected copy.")
            if pdf.page_count == 0:
                raise InvalidFile("The PDF has no pages.")
            if pdf.page_count > MAX_PDF_PAGES:
                raise InvalidFile(f"The PDF has more than {MAX_PDF_PAGES} pages.")
    except InvalidFile:
        raise
    except Exception:
        raise InvalidFile("The PDF could not be opened. It may be damaged.")


def _check_text(path: str, extension: str) -> None:
    with open(path, "rb") as handle:
        data = handle.read()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InvalidFile("Text files must be UTF-8.")
    if not text.strip():
        raise InvalidFile("The file is empty.")
    if extension == "json":
        try:
            json.loads(text)
        except ValueError:
            raise InvalidFile("The JSON file is not valid JSON.")


def check_upload(uploaded) -> CheckedFile:
    filename = safe_filename(uploaded.name or "")
    extension = extension_of(filename)
    if extension not in FORMATS:
        raise UnsupportedFileType(f"'.{extension or '?'}' files are not supported. Allowed: {', '.join(sorted(FORMATS))}.")
    if uploaded.size is not None and uploaded.size > settings.UPLOAD_MAX_BYTES:
        raise FileTooLarge(f"The file is larger than {settings.UPLOAD_MAX_BYTES // (1024 * 1024)} MB.")
    path, size, sha256 = _copy_and_hash(uploaded)
    try:
        if size == 0:
            raise InvalidFile("The file is empty.")
        sniffed = magic.from_file(path, mime=True)
        allowed, stored_mime = FORMATS[extension]
        if sniffed not in allowed and not (sniffed.startswith("text/") and TEXT_FAMILY & allowed):
            raise UnsupportedFileType(f"The file content ({sniffed}) does not match its .{extension} name.")
        if extension in OFFICE_MAIN_PART:
            _check_office(path, extension)
        elif extension == "pdf":
            _check_pdf(path)
        else:
            _check_text(path, extension)
    except Exception:
        os.unlink(path)
        raise
    return CheckedFile(path=path, filename=filename, extension=extension, mime_type=stored_mime, size=size, sha256=sha256)
