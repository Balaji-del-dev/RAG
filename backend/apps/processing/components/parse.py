"""Steps 1-3: read the original, parse it (Docling / PyMuPDF / plain readers), OCR pages with too little text."""

import csv
import hashlib
import io
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET  # noqa: S405 — expat in Python 3.12 limits entity expansion
from functools import lru_cache

from django.conf import settings

from apps.core.clients import storage

from .base import ContentError, Context, Element, TransientError

DOCLING_FORMATS = {"pdf", "docx", "pptx", "xlsx", "html", "htm", "md"}
PLAIN_FORMATS = {"txt", "csv", "json", "xml"}

DOCLING_LABELS = {
    "title": ("TITLE", 1),
    "section_header": ("HEADING", 2),
    "text": ("PARAGRAPH", 0),
    "paragraph": ("PARAGRAPH", 0),
    "list_item": ("LIST_ITEM", 0),
    "caption": ("CAPTION", 0),
    "code": ("CODE", 0),
    "footnote": ("FOOTNOTE", 0),
    "page_header": ("PAGE_HEADER", 0),
    "page_footer": ("PAGE_FOOTER", 0),
    "formula": ("PARAGRAPH", 0),
    "reference": ("PARAGRAPH", 0),
}


# ---------------------------------------------------------------- step 1


def read_original(ctx: Context, config: dict) -> dict:
    version = ctx.version
    path = ctx.workdir / f"original.{ctx.extension}"
    try:
        storage.download_to(version.storage_bucket, version.storage_object_key, str(path), version.storage_version_id)
    except Exception as exc:
        raise TransientError(f"could not read the original from MinIO: {exc}") from exc
    if config.get("verify_sha256", True):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != version.content_sha256:
            raise ContentError("The stored file does not match its SHA-256. It may have been changed in MinIO.")
    ctx.original_path = path
    return {"bytes": path.stat().st_size, "sha256_checked": bool(config.get("verify_sha256", True))}


# ---------------------------------------------------------------- step 2


@lru_cache(maxsize=1)
def _docling_converter(table_structure: bool):
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(
        artifacts_path=settings.DOCLING_ARTIFACTS_DIR,
        do_ocr=False,  # our own OCR step handles scanned pages
        do_table_structure=table_structure,
        accelerator_options=AcceleratorOptions(num_threads=settings.TORCH_THREADS, device="cpu"),
    )
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})


def _parse_with_docling(ctx: Context, config: dict) -> list[Element]:
    from docling_core.types.doc import TableItem

    result = _docling_converter(bool(config.get("table_structure", True))).convert(
        str(ctx.original_path), max_num_pages=int(config.get("max_pages", 500))
    )
    doc = result.document
    elements: list[Element] = []
    for item, _level in doc.iterate_items():
        label = getattr(getattr(item, "label", None), "value", "")
        page = item.prov[0].page_no if getattr(item, "prov", None) else None
        if isinstance(item, TableItem):
            text = item.export_to_markdown(doc=doc).strip()
            if text:
                elements.append(Element("TABLE", text, page))
            continue
        text = (getattr(item, "text", "") or "").strip()
        if not text or label not in DOCLING_LABELS:
            continue
        element_type, heading_level = DOCLING_LABELS[label]
        level = getattr(item, "level", heading_level) if element_type == "HEADING" else heading_level
        elements.append(Element(element_type, text, page, level=int(level or heading_level)))
    ctx.page_count = len(doc.pages) if getattr(doc, "pages", None) else ctx.page_count
    return elements


def _paragraphs(text: str, page: int | None = None) -> list[Element]:
    return [Element("PARAGRAPH", block.strip(), page) for block in text.replace("\r\n", "\n").split("\n\n") if block.strip()]


def _parse_plain(ctx: Context, config: dict) -> list[Element]:
    raw = ctx.original_path.read_bytes()[: int(config.get("max_chars", 5_000_000)) * 4]
    try:
        text = raw.decode(
            config.get("encoding", "utf-8") + "-sig" if config.get("encoding", "utf-8") == "utf-8" else config["encoding"]
        )
    except (UnicodeDecodeError, LookupError) as exc:
        raise ContentError(f"The text could not be decoded: {exc}") from exc
    ext = ctx.extension
    if ext == "csv":
        rows = list(csv.reader(io.StringIO(text)))
        if not rows:
            raise ContentError("The CSV file has no rows.")
        header, body = rows[0], rows[1:]
        lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
        lines += ["| " + " | ".join(cell.replace("|", "/") for cell in row) + " |" for row in body]
        return [Element("TABLE", "\n".join(lines))]
    if ext == "json":
        data = json.loads(text)
        return _flatten_json(data)
    if ext == "xml":
        try:
            root = ET.fromstring(text)  # noqa: S314
        except ET.ParseError as exc:
            raise ContentError(f"The XML file is not well-formed: {exc}") from exc
        return [Element("PARAGRAPH", " ".join(node.text.split())) for node in root.iter() if node.text and node.text.strip()]
    return _paragraphs(text)


def _flatten_json(data, path: str = "") -> list[Element]:
    """Each leaf becomes 'a.b[0].c: value'; grouped by top-level key so related values stay together."""
    lines: list[str] = []

    def walk(value, prefix: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, f"{prefix}.{key}" if prefix else str(key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{prefix}[{index}]")
        else:
            lines.append(f"{prefix}: {value}")

    walk(data, path)
    blocks, current = [], []
    for line in lines:
        current.append(line)
        if len(current) >= 20:
            blocks.append("\n".join(current))
            current = []
    if current:
        blocks.append("\n".join(current))
    return [Element("PARAGRAPH", block) for block in blocks]


def _parse_with_pymupdf(ctx: Context, config: dict) -> list[Element]:
    import pymupdf

    elements: list[Element] = []
    with pymupdf.open(str(ctx.original_path)) as pdf:
        ctx.page_count = pdf.page_count
        for page in pdf.pages(0, min(pdf.page_count, int(config.get("max_pages", 500)))):
            elements += _paragraphs(page.get_text("text"), page.number + 1)
    return elements


def parse_docling(ctx: Context, config: dict) -> dict:
    """Docling for PDF/Office/HTML/Markdown; the plain readers for TXT, CSV, JSON and XML."""
    if ctx.extension in PLAIN_FORMATS:
        ctx.elements = _parse_plain(ctx, {})
        parser = "plain"
    elif ctx.extension in DOCLING_FORMATS:
        try:
            ctx.elements = _parse_with_docling(ctx, config)
            parser = "docling"
        except Exception as exc:
            if ctx.extension != "pdf":
                raise ContentError(f"The document could not be parsed: {exc}") from exc
            ctx.elements = _parse_with_pymupdf(ctx, config)  # PDF fallback
            ctx.notes["docling_error"] = str(exc)[:300]
            parser = "pymupdf"
    else:
        raise ContentError(f"No parser for .{ctx.extension} files.")
    if ctx.extension == "pdf" and ctx.page_count is None:
        import pymupdf

        with pymupdf.open(str(ctx.original_path)) as pdf:
            ctx.page_count = pdf.page_count
    return {"parser": parser, "elements": len(ctx.elements), "pages": ctx.page_count}


def parse_pymupdf(ctx: Context, config: dict) -> dict:
    if ctx.extension != "pdf":
        return parse_docling(ctx, {})
    ctx.elements = _parse_with_pymupdf(ctx, config)
    return {"parser": "pymupdf", "elements": len(ctx.elements), "pages": ctx.page_count}


def parse_plain(ctx: Context, config: dict) -> dict:
    ctx.elements = _parse_plain(ctx, config)
    return {"parser": "plain", "elements": len(ctx.elements)}


# ---------------------------------------------------------------- step 3


@lru_cache(maxsize=1)
def installed_tesseract_languages() -> set[str]:
    if not shutil.which("tesseract"):
        return set()
    output = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, check=False).stdout  # noqa: S607
    return {line.strip() for line in output.splitlines()[1:] if line.strip()}


def ocr_tesseract(ctx: Context, config: dict) -> dict:
    """OCR only the PDF pages whose extracted text is shorter than min_chars_per_page."""
    if ctx.extension != "pdf" or not ctx.page_count:
        return {"skipped": True, "reason": "not a PDF"}
    import pymupdf
    import pytesseract
    from PIL import Image

    wanted = config.get("languages", "eng").split("+")
    available = installed_tesseract_languages()
    languages = [lang for lang in wanted if lang in available] or (["eng"] if "eng" in available else [])
    if not languages:
        return {"skipped": True, "reason": "Tesseract is not installed"}
    chars: dict[int, int] = {}
    for element in ctx.elements:
        if element.page:
            chars[element.page] = chars.get(element.page, 0) + len(element.text)
    threshold = int(config.get("min_chars_per_page", 50))
    pages = [n for n in range(1, ctx.page_count + 1) if chars.get(n, 0) < threshold]
    if not pages:
        return {"pages_ocred": 0, "languages": "+".join(languages)}
    added = 0
    with pymupdf.open(str(ctx.original_path)) as pdf:
        for number in pages:
            pixmap = pdf[number - 1].get_pixmap(dpi=int(config.get("dpi", 200)))
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            text = pytesseract.image_to_string(image, lang="+".join(languages))
            for element in _paragraphs(text, number):
                element.source = "ocr"
                ctx.elements.append(element)
                added += 1
    ctx.elements.sort(key=lambda e: e.page or 0)
    return {
        "pages_ocred": len(pages),
        "elements_added": added,
        "languages": "+".join(languages),
        "missing_languages": sorted(set(wanted) - available),
    }


def ocr_easyocr(ctx: Context, config: dict) -> dict:
    return {"skipped": True, "reason": "EasyOCR is a fallback; Tesseract is used in the baseline"}
