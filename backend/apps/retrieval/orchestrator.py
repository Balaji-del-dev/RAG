"""Question -> grounded, cited answer (docs/images/05-query-flow.png). Runs in a worker thread; emits events."""

import re
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import structlog
from django.db import transaction

from apps.accounts.selectors import access_scope
from apps.core.clients import embedder, llm, reranker, search_index, vector_store
from apps.documents.models import Document
from apps.documents.selectors import visible_documents
from apps.indexing.models import IndexGeneration
from apps.indexing.services import live_generation
from apps.processing.components.text import with_header
from apps.processing.models import Chunk
from apps.registry.components import AbstentionSettings, CitationSettings, GenerateLiteLLM, RetrievalSettings

from .models import AnswerRecord, RetrievalResult, RetrievalRun

log = structlog.get_logger(__name__)

Emit = Callable[[str, dict], None]
CITATION = re.compile(r"\[(\d{1,2})\]")
MAX_QUESTION = 2000
# Greetings and thanks get a friendly reply, not a search ("hi" is not a question about the documents).
SMALL_TALK = re.compile(
    r"^(hi+|hello|hey|hai|good (morning|afternoon|evening)|thanks?( you)?|thank u|ok(ay)?|bye|how are you)[\s!.,?]*$", re.I
)
SMALL_TALK_REPLY = (
    "Hello! Ask me anything about the documents you can access, for example "
    '"Give me a summary of …", "What are the rules for …?" or "Which projects use …?".'
)


@dataclass
class Candidate:
    chunk_id: str
    dense_rank: int | None = None
    dense_score: float | None = None
    bm25_rank: int | None = None
    bm25_score: float | None = None
    fusion: float = 0.0
    fusion_rank: int | None = None
    rerank: float | None = None
    chunk: Chunk | None = None

    @property
    def source(self) -> str:
        if self.dense_rank is not None and self.bm25_rank is not None:
            return RetrievalResult.Source.BOTH
        return RetrievalResult.Source.DENSE if self.dense_rank is not None else RetrievalResult.Source.LEXICAL


class QuestionError(ValueError):
    pass


def normalize(question: str) -> str:
    return " ".join(question.split())


def rrf(candidates: dict[str, Candidate], k: int) -> list[Candidate]:
    """Reciprocal rank fusion: score = Σ 1 / (k + rank) over the lists a chunk appears in."""
    for c in candidates.values():
        c.fusion = sum(1.0 / (k + rank) for rank in (c.dense_rank, c.bm25_rank) if rank is not None)
    ranked = sorted(candidates.values(), key=lambda c: c.fusion, reverse=True)
    for position, c in enumerate(ranked, start=1):
        c.fusion_rank = position
    return ranked


def pick_context(
    ranked: list[Candidate], *, max_chunks: int, max_tokens: int, min_score: float, max_gap: float | None = None
) -> list[Candidate]:
    chosen, tokens = [], 0
    ordered = sorted(ranked, key=lambda c: c.rerank if c.rerank is not None else -1e9, reverse=True)
    floor = (
        min_score if max_gap is None or not ordered or ordered[0].rerank is None else max(min_score, ordered[0].rerank - max_gap)
    )
    for c in ordered:
        if c.rerank is None or c.rerank < floor or len(chosen) >= max_chunks:
            break
        if tokens + c.chunk.token_count > max_tokens and chosen:
            continue
        chosen.append(c)
        tokens += c.chunk.token_count
    return chosen


def rerank_text(c: Candidate, contextual: bool) -> str:
    if not contextual:
        return c.chunk.text_content
    chunk = c.chunk
    return with_header(chunk.text_content, filename=chunk.document_version.document.filename, section_path=chunk.section_path)


def format_sources(context: list[Candidate], show_sections: bool = False) -> str:
    blocks = []
    for n, c in enumerate(context, start=1):
        where = c.chunk.document_version.document.filename
        if show_sections and c.chunk.section_path:
            where += f", section: {c.chunk.section_path}"
        if c.chunk.page_start:
            where += f", page {c.chunk.page_start}"
        blocks.append(f"[{n}] ({where})\n{c.chunk.text_content}")
    return "\n\n".join(blocks)


def check_citations(text: str, source_count: int, require: bool) -> tuple[bool, list[int], str]:
    """(ok, cited numbers, problem). NO_ANSWER is handled by the caller."""
    cited = sorted({int(n) for n in CITATION.findall(text)})
    invalid = [n for n in cited if not 1 <= n <= source_count]
    if invalid:
        return False, cited, f"it cites sources that do not exist: {invalid}"
    if not re.sub(r"[\W_]+", "", CITATION.sub("", text)):
        return False, cited, "it has no answer text, only source numbers"
    if require and not cited:
        return False, cited, "it has no citations"
    return True, cited, ""


def is_no_answer(text: str) -> bool:
    return text.strip().upper().startswith("NO_ANSWER") or not text.strip()


def answer(
    *,
    user,
    question: str,
    emit: Emit,
    generation: IndexGeneration | None = None,
    scope: list[str] | None = None,
    on_context: Callable[[list[Candidate]], None] | None = None,
) -> RetrievalRun | None:
    """Answer one question. `scope` overrides the user's access groups (evaluation ACCESS cases only)."""
    started = time.monotonic()
    normalized = normalize(question)
    if not normalized:
        raise QuestionError("Type a question first.")
    if len(question) > MAX_QUESTION:
        raise QuestionError(f"Questions can be at most {MAX_QUESTION} characters.")
    if SMALL_TALK.match(normalized):
        emit("abstain", {"message": SMALL_TALK_REPLY, "reason": "small_talk"})
        return None
    generation = generation or live_generation()
    if generation is None:
        emit("abstain", {"message": "No documents have been published for search yet.", "reason": "no_live_index"})
        return None
    pipeline_version = generation.pipeline_version
    settings_ = RetrievalSettings.model_validate(
        {f: getattr(pipeline_version.retrieval_definition, f) for f in RetrievalSettings.model_fields}
    )
    gen_def = pipeline_version.generation_definition
    gen_cfg = GenerateLiteLLM.model_validate(gen_def.generation_config)
    cite_cfg = CitationSettings.model_validate(gen_def.citation_config)
    abstain_cfg = AbstentionSettings.model_validate(gen_def.abstention_config)
    scope = sorted(scope) if scope is not None else sorted(access_scope(user))
    scoped = Document.objects.filter(deleted_at__isnull=True, access_grants__access_group__name__in=scope)
    request_id = uuid.uuid4()
    run = RetrievalRun.objects.create(
        request_id=request_id, user=user, query_text=question, normalized_query=normalized,
        pipeline_version=pipeline_version, index_generation=generation, trace_id=request_id.hex,
    )  # fmt: skip
    emit("meta", {"run_id": str(run.pk), "request_id": str(request_id)})
    structlog.contextvars.bind_contextvars(trace_id=request_id.hex, run_id=str(run.pk))

    # ---- 1. both searches in parallel, the same mandatory filter: generation + access groups
    emit("status", {"stage": "searching"})
    gid = str(generation.pk)
    with ThreadPoolExecutor(max_workers=2) as pool:
        dense_future = pool.submit(
            lambda: vector_store.search(
                generation.qdrant_collection,
                embedder.embed_query(normalized, prefix=settings_.dense_config.query_prefix).tolist(),
                generation_id=gid,
                access_groups=scope,
                limit=settings_.dense_config.top_k,
            )  # fmt: skip
        )
        lexical_future = pool.submit(
            lambda: search_index.search(
                generation.opensearch_index,
                normalized,
                generation_id=gid,
                access_groups=scope,
                size=settings_.bm25_config.top_k,
                fields=settings_.bm25_config.fields,
                fuzziness=settings_.bm25_config.fuzziness,
            )  # fmt: skip
        )
        dense, lexical = dense_future.result(), lexical_future.result()
    candidates: dict[str, Candidate] = {}
    for rank, point in enumerate(dense, start=1):
        c = candidates.setdefault(str(point.id), Candidate(str(point.id)))
        c.dense_rank, c.dense_score = rank, float(point.score)
    for rank, hit in enumerate(lexical, start=1):
        c = candidates.setdefault(hit["_id"], Candidate(hit["_id"]))
        c.bm25_rank, c.bm25_score = rank, float(hit["_score"])

    # ---- 2. fuse, then load the canonical text — re-checking access in PostgreSQL (defence in depth)
    ranked = rrf(candidates, settings_.fusion_config.k)
    visible = scoped.values("pk") if not user.has_perm("accounts.manage") else visible_documents(user).values("pk")
    chunks = {
        str(c.pk): c
        for c in Chunk.objects.filter(pk__in=list(candidates), document_version__document__in=visible).select_related(
            "document_version__document"
        )
    }
    ranked = [c for c in ranked if c.chunk_id in chunks]
    for c in ranked:
        c.chunk = chunks[c.chunk_id]

    # ---- 3. rerank the best of the fused list
    emit("status", {"stage": "reranking"})
    top = ranked[: settings_.reranker_config.top_n]
    contextual = settings_.reranker_config.contextual
    for c, s in zip(top, reranker.score(normalized, [rerank_text(c, contextual) for c in top]), strict=True):
        c.rerank = s
    RetrievalResult.objects.bulk_create(
        RetrievalResult(
            retrieval_run=run,
            chunk_id=c.chunk_id,
            retrieval_source=c.source,
            original_rank=min(r for r in (c.dense_rank, c.bm25_rank) if r is not None),
            original_score=c.dense_score if c.dense_score is not None else (c.bm25_score or 0.0),
            fusion_rank=c.fusion_rank,
            reranker_score=c.rerank,
        )  # fmt: skip
        for c in ranked
    )
    context = pick_context(
        top,
        max_chunks=settings_.context_config.max_chunks,
        max_tokens=settings_.context_config.max_tokens,
        min_score=settings_.context_config.min_rerank_score,
        max_gap=settings_.context_config.max_gap_from_best,
    )
    model_def = gen_def.model
    if on_context is not None:
        on_context(context)

    def finish(status_run: str, status_answer: str, text: str | None, citations: list[dict], usage: llm.Usage, latency: int):
        with transaction.atomic():
            record = AnswerRecord.objects.create(
                retrieval_run=run, model=model_def, prompt_version=gen_def.name, answer_text=text, citation_data=citations,
                status=status_answer, latency_ms=latency,
                token_usage_json={"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens},
            )  # fmt: skip
            run.status = status_run
            run.latency_ms = int((time.monotonic() - started) * 1000)
            run.save(update_fields=["status", "latency_ms"])
        return record

    if not context:
        record = finish(RetrievalRun.Status.ABSTAINED, AnswerRecord.Status.ABSTAINED, None, [], llm.Usage(), 0)
        emit("abstain", {"answer_id": str(record.pk), "message": abstain_cfg.message, "reason": "no_evidence"})
        return run

    # ---- 4. grounded generation, streamed as a draft
    emit("status", {"stage": "writing"})
    sources = format_sources(context, show_sections=settings_.context_config.show_sections)
    prompt = gen_def.prompt_template.format(sources=sources, question=normalized)
    usage = llm.Usage()
    t0 = time.monotonic()
    text = ""
    try:
        for piece in llm.stream(model_def.model_name, prompt, temperature=gen_cfg.temperature, max_tokens=gen_cfg.max_tokens,
                                timeout=gen_cfg.timeout_seconds, num_ctx=gen_cfg.num_ctx, usage=usage):  # fmt: skip
            text += piece
            emit("token", {"text": piece})
    except llm.LLMUnavailableError as exc:
        run.status = RetrievalRun.Status.FAILED
        run.latency_ms = int((time.monotonic() - started) * 1000)
        run.save(update_fields=["status", "latency_ms"])
        log.warning("retrieval.llm_unavailable", error=str(exc))
        emit("error", {"code": "llm_unavailable", "message": "The local language model did not answer. Try again in a minute."})
        return run

    # ---- 5. validate: citations must point at given sources; repair once or abstain
    emit("status", {"stage": "checking"})
    answer_status = AnswerRecord.Status.VALIDATED
    if not is_no_answer(text):
        ok, cited, problem = check_citations(text, len(context), cite_cfg.require_citation)
        attempts = cite_cfg.repair_attempts
        while not ok and attempts > 0:
            attempts -= 1
            repair_prompt = (
                f"{prompt}\n\nYour previous answer was rejected because {problem}. "
                "Answer again, citing only the numbered sources above like [1]. "
                "If they do not contain the answer, reply NO_ANSWER."
            )
            try:
                text = llm.complete(model_def.model_name, repair_prompt, temperature=0.0, max_tokens=gen_cfg.max_tokens,
                                    timeout=gen_cfg.timeout_seconds, num_ctx=gen_cfg.num_ctx, usage=usage)  # fmt: skip
            except llm.LLMUnavailableError:
                break
            if is_no_answer(text):
                break
            ok, cited, problem = check_citations(text, len(context), cite_cfg.require_citation)
            answer_status = AnswerRecord.Status.REPAIRED
        if not is_no_answer(text) and not ok:
            record = finish(
                RetrievalRun.Status.REJECTED, AnswerRecord.Status.REJECTED, text, [], usage, int((time.monotonic() - t0) * 1000)
            )
            emit("abstain", {"answer_id": str(record.pk), "message": abstain_cfg.message, "reason": "unverified_answer"})
            return run
    if is_no_answer(text):
        record = finish(
            RetrievalRun.Status.ABSTAINED, AnswerRecord.Status.ABSTAINED, None, [], usage, int((time.monotonic() - t0) * 1000)
        )
        emit("abstain", {"answer_id": str(record.pk), "message": abstain_cfg.message, "reason": "model_found_no_answer"})
        return run

    citations = [
        {
            "n": n,
            "chunk_id": context[n - 1].chunk_id,
            "document_id": str(context[n - 1].chunk.document_version.document_id),
            "filename": context[n - 1].chunk.document_version.document.filename,
            "page_start": context[n - 1].chunk.page_start,
            "page_end": context[n - 1].chunk.page_end,
            "section_path": context[n - 1].chunk.section_path or "",
        }
        for n in cited
    ]
    record = finish(
        RetrievalRun.Status.ANSWERED, answer_status, text.strip(), citations, usage, int((time.monotonic() - t0) * 1000)
    )
    emit("done", {"answer_id": str(record.pk), "answer": text.strip(), "citations": citations, "status": answer_status})
    log.info("retrieval.answered", latency_ms=run.latency_ms, sources=len(context), citations=len(citations))
    return run
