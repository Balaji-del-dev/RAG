"""Shared types for the ingestion steps. Each step reads and writes the job's Context."""

import uuid
from dataclasses import dataclass, field
from pathlib import Path


class ContentError(Exception):
    """The file itself is the problem (unreadable, empty). Not retried; the message is shown to the user."""


class TransientError(Exception):
    """A service hiccup (MinIO, database). The job is retried with backoff."""


@dataclass
class Element:
    """One structured piece of a document: a heading, paragraph, table, …"""

    type: str  # DocumentElementType value
    text: str
    page: int | None = None
    level: int = 0  # heading depth (1 = top)
    section_path: str = ""
    source: str = "parser"  # parser | ocr


@dataclass
class ChunkDraft:
    text: str
    page_start: int | None
    page_end: int | None
    section_path: str
    token_count: int = 0
    kind: str = "text"  # text | table
    table_group: int | None = None  # chunks split from one table share a number
    content_hash: str = ""
    id: uuid.UUID | None = None


@dataclass
class Context:
    job: object
    version: object  # DocumentVersion
    pipeline_version: object
    workdir: Path
    original_path: Path | None = None
    elements: list[Element] = field(default_factory=list)
    chunks: list[ChunkDraft] = field(default_factory=list)
    page_count: int | None = None
    notes: dict = field(default_factory=dict)

    @property
    def extension(self) -> str:
        return self.version.document.file_extension
