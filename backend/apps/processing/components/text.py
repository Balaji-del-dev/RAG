"""Steps 4-6: normalize text, rebuild the document structure (section paths), enrichment (none)."""

import re
import unicodedata

from django.db import transaction

from apps.processing.models import DocumentElement

from .base import ContentError, Context

HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
SPACES = re.compile(r"[ \t ]+")
MANY_NEWLINES = re.compile(r"\n{3,}")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize_text(text: str, *, form: str = "NFKC", fix_hyphenation: bool = True, collapse_whitespace: bool = True) -> str:
    text = unicodedata.normalize(form, text)
    text = CONTROL.sub("", text)
    if fix_hyphenation:
        text = HYPHEN_BREAK.sub(r"\1\2", text)
    if collapse_whitespace:
        text = SPACES.sub(" ", text)
        text = MANY_NEWLINES.sub("\n\n", text)
        text = "\n".join(line.strip() for line in text.split("\n"))
    return text.strip()


def clean_normalize(ctx: Context, config: dict) -> dict:
    before = sum(len(e.text) for e in ctx.elements)
    for element in ctx.elements:
        keep_lines = element.type in ("TABLE", "CODE")
        element.text = normalize_text(
            element.text,
            form=config.get("unicode_form", "NFKC"),
            fix_hyphenation=bool(config.get("fix_hyphenation", True)) and not keep_lines,
            collapse_whitespace=bool(config.get("collapse_whitespace", True)) and not keep_lines,
        )
    ctx.elements = [e for e in ctx.elements if e.text]
    after = sum(len(e.text) for e in ctx.elements)
    if not ctx.elements:
        raise ContentError("No text was found in the document (even after OCR).")
    return {"elements": len(ctx.elements), "chars_before": before, "chars_after": after}


def _markdown_heading(element) -> None:
    """Markdown and plain text: turn '# Title' paragraphs into headings."""
    match = re.match(r"^(#{1,6})\s+(.+)$", element.text)
    if element.type == "PARAGRAPH" and match and "\n" not in element.text:
        element.type, element.level, element.text = "HEADING", len(match.group(1)), match.group(2).strip()


def structure_rebuild(ctx: Context, config: dict) -> dict:
    """Give every element its section path (Heading 1 > Heading 2 > …) and save document_elements."""
    if config.get("drop_page_headers_footers", True):
        ctx.elements = [e for e in ctx.elements if e.type not in ("PAGE_HEADER", "PAGE_FOOTER")]
    stack: list[tuple[int, str]] = []
    headings = 0
    for element in ctx.elements:
        if ctx.extension in ("md", "txt"):
            _markdown_heading(element)
        if element.type in ("TITLE", "HEADING"):
            # A document title sits above every heading level (Docling reports '#' and '##' both as level 1).
            level = 0 if element.type == "TITLE" else max(1, element.level or 1)
            stack = [(lvl, title) for lvl, title in stack if lvl < level]
            stack.append((level, element.text[:120]))
            headings += 1
        element.section_path = " > ".join(title for _, title in stack)

    with transaction.atomic():
        DocumentElement.objects.filter(document_version=ctx.version).delete()
        DocumentElement.objects.bulk_create(
            DocumentElement(
                document_version=ctx.version,
                element_type=e.type,
                element_order=order,
                page_number=e.page,
                section_path=e.section_path or None,
                text_content=e.text,
                metadata_json={"source": e.source, "level": e.level},
            )
            for order, e in enumerate(ctx.elements)
        )
    types: dict[str, int] = {}
    for e in ctx.elements:
        types[e.type] = types.get(e.type, 0) + 1
    return {"elements": len(ctx.elements), "headings": headings, "types": types}


def enrich_none(ctx: Context, config: dict) -> dict:
    return {"skipped": True, "reason": "no enrichment in the baseline"}


def document_title(filename: str) -> str:
    """'Balamurugan_Thangadurai_CV.pdf' -> 'Balamurugan Thangadurai CV'."""
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return " ".join(stem.replace("_", " ").split())


def with_header(text: str, *, filename: str, section_path: str | None) -> str:
    """A chunk with its contextual header: '<document title> > <section>' on the first line."""
    header = document_title(filename)
    if section_path:
        header += f" > {section_path}"
    return f"{header}\n{text}"
