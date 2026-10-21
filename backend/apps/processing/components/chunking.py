"""Steps 7-8: structure-aware chunks (≤ max tokens, with overlap; tables whole or split by rows) and quality checks."""

import hashlib
import re

from apps.core.clients import embedder

from .base import ChunkDraft, Context, Element

SENTENCE_END = re.compile(r"(?<=[.!?।])\s+")


def _tokens(text: str) -> int:
    return embedder.count_tokens(text)


def _with_heading(section_path: str, body: str) -> str:
    return f"{section_path}\n\n{body}" if section_path else body


def _split_long(text: str, max_tokens: int) -> list[str]:
    """Split one very long paragraph at sentence ends; hard-split as a last resort."""
    pieces, current = [], ""
    for sentence in SENTENCE_END.split(text):
        candidate = f"{current} {sentence}".strip()
        if current and _tokens(candidate) > max_tokens:
            pieces.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        pieces.append(current)
    result = []
    for piece in pieces:
        while _tokens(piece) > max_tokens:
            ids = embedder.tokenizer().encode(piece, add_special_tokens=False)
            head = embedder.tokenizer().decode(ids[:max_tokens])
            result.append(head)
            piece = embedder.tokenizer().decode(ids[max_tokens:])
        if piece.strip():
            result.append(piece)
    return result


def _overlap_tail(text: str, overlap_tokens: int) -> str:
    """The last sentences of a chunk, up to overlap_tokens, to start the next chunk with."""
    if overlap_tokens <= 0:
        return ""
    tail: list[str] = []
    for sentence in reversed(SENTENCE_END.split(text)):
        if _tokens(" ".join([sentence, *tail])) > overlap_tokens:
            break
        tail.insert(0, sentence)
    return " ".join(tail)


def _table_chunks(element: Element, max_tokens: int, keep_whole: bool, group: int) -> list[ChunkDraft]:
    text = _with_heading(element.section_path, element.text)
    if keep_whole and _tokens(text) <= max_tokens:
        return [ChunkDraft(text, element.page, element.page, element.section_path, kind="table", table_group=group)]
    lines = element.text.split("\n")
    header = lines[:2] if len(lines) > 1 and set(lines[1].replace("|", "").strip()) <= {"-", ":", " "} else lines[:1]
    rows = lines[len(header) :]
    chunks, current = [], []
    for row in rows:
        candidate = _with_heading(element.section_path, "\n".join([*header, *current, row]))
        if current and _tokens(candidate) > max_tokens:
            chunks.append(_with_heading(element.section_path, "\n".join([*header, *current])))
            current = [row]
        else:
            current.append(row)
    if current or not chunks:
        chunks.append(_with_heading(element.section_path, "\n".join([*header, *current])))
    return [ChunkDraft(c, element.page, element.page, element.section_path, kind="table", table_group=group) for c in chunks]


def chunk_structure_aware(ctx: Context, config: dict) -> dict:
    max_tokens = int(config.get("max_tokens", 400))
    overlap = int(config.get("overlap_tokens", 50))
    keep_tables = bool(config.get("keep_tables_whole", True))
    chunks: list[ChunkDraft] = []
    buffer: list[str] = []
    pages: list[int] = []
    section = ""
    table_group = 0

    def flush(carry: bool) -> str:
        nonlocal buffer, pages
        if not buffer:
            return ""
        body = "\n\n".join(buffer)
        chunks.append(ChunkDraft(_with_heading(section, body), min(pages, default=None), max(pages, default=None), section))
        tail = _overlap_tail(body, overlap) if carry else ""
        buffer, pages = ([tail] if tail else []), (pages[-1:] if tail else [])
        return tail

    for element in ctx.elements:
        if element.section_path != section:
            flush(carry=False)
            section = element.section_path
        if element.type in ("TITLE", "HEADING"):
            continue  # headings live in each chunk's section line
        if element.type == "TABLE":
            flush(carry=False)
            table_group += 1
            chunks.extend(_table_chunks(element, max_tokens, keep_tables, table_group))
            continue
        budget = max_tokens - _tokens(_with_heading(section, ""))
        for piece in _split_long(element.text, max(32, budget)) if _tokens(element.text) > budget else [element.text]:
            candidate = "\n\n".join([*buffer, piece])
            if buffer and _tokens(_with_heading(section, candidate)) > max_tokens:
                flush(carry=True)
            buffer.append(piece)
            if element.page:
                pages.append(element.page)
    flush(carry=False)

    for chunk in chunks:
        chunk.token_count = _tokens(chunk.text)
    ctx.chunks = chunks
    return {
        "chunks": len(chunks),
        "tables": sum(1 for c in chunks if c.kind == "table"),
        "max_tokens_seen": max((c.token_count for c in chunks), default=0),
    }


def chunk_quality_checks(ctx: Context, config: dict) -> dict:
    min_tokens = int(config.get("min_tokens", 5))
    max_tokens = int(config.get("max_tokens", 480))
    seen: set[str] = set()
    kept: list[ChunkDraft] = []
    dropped = {"empty": 0, "too_short": 0, "duplicate": 0, "oversized_split": 0, "broken_table": 0}
    for chunk in ctx.chunks:
        text = chunk.text.strip()
        if not text:
            dropped["empty"] += 1
            continue
        if chunk.kind == "table" and text.count("\n") < 2:
            dropped["broken_table"] += 1  # only a header row: nothing to find
            continue
        if chunk.token_count < min_tokens and len(ctx.chunks) > 1:
            dropped["too_short"] += 1
            continue
        chunk.content_hash = hashlib.sha256(text.encode()).hexdigest()
        if config.get("drop_duplicates", True) and chunk.content_hash in seen:
            dropped["duplicate"] += 1
            continue
        seen.add(chunk.content_hash)
        if chunk.token_count > max_tokens:
            dropped["oversized_split"] += 1
            for piece in _split_long(text, max_tokens):
                kept.append(
                    ChunkDraft(
                        piece,
                        chunk.page_start,
                        chunk.page_end,
                        chunk.section_path,
                        _tokens(piece),
                        chunk.kind,
                        chunk.table_group,
                        hashlib.sha256(piece.encode()).hexdigest(),
                    )  # fmt: skip
                )
            continue
        kept.append(chunk)
    if not kept:
        from .base import ContentError

        raise ContentError("No usable text chunks were produced from this document.")
    ctx.chunks = kept
    return {"kept": len(kept), "dropped": dropped}
