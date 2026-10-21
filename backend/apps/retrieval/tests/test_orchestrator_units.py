from types import SimpleNamespace

import pytest

from apps.processing.components.text import document_title, with_header
from apps.retrieval.orchestrator import SMALL_TALK, Candidate, check_citations, is_no_answer, pick_context, rerank_text, rrf


def test_rrf_rewards_chunks_found_by_both_engines():
    candidates = {
        "a": Candidate("a", dense_rank=1),
        "b": Candidate("b", dense_rank=2, bm25_rank=2),
        "c": Candidate("c", bm25_rank=1),
    }
    ranked = rrf(candidates, k=60)
    assert [c.chunk_id for c in ranked] == ["b", "a", "c"]
    assert ranked[0].fusion == 2 / 62 and ranked[0].source == "BOTH"
    assert [c.fusion_rank for c in ranked] == [1, 2, 3]


def chunk(tokens):
    return SimpleNamespace(token_count=tokens)


def test_context_keeps_the_best_chunks_within_budget_and_threshold():
    ranked = [
        Candidate(str(i), rerank=score, chunk=chunk(t)) for i, (score, t) in enumerate([(9, 600), (8, 600), (7, 600), (-9, 10)])
    ]
    chosen = pick_context(ranked, max_chunks=4, max_tokens=1500, min_score=-5)
    assert [c.chunk_id for c in chosen] == ["0", "1"]  # the third would exceed 1500 tokens; the last is below the threshold
    assert pick_context([Candidate("x", rerank=-9, chunk=chunk(10))], max_chunks=4, max_tokens=1500, min_score=-5) == []


def test_context_can_also_drop_chunks_far_below_the_best_one():
    ranked = [Candidate(str(i), rerank=score, chunk=chunk(50)) for i, score in enumerate([5.3, -9.3, -9.6])]
    assert [c.chunk_id for c in pick_context(ranked, max_chunks=5, max_tokens=1200, min_score=-9.5)] == ["0", "1"]
    assert [c.chunk_id for c in pick_context(ranked, max_chunks=5, max_tokens=1200, min_score=-9.5, max_gap=8)] == ["0"]
    weak = [Candidate(str(i), rerank=score, chunk=chunk(50)) for i, score in enumerate([-8.7, -8.9, -9.0])]
    assert len(pick_context(weak, max_chunks=5, max_tokens=1200, min_score=-9.5, max_gap=8)) == 3  # a typo'd question


def test_citations_must_point_at_given_sources():
    assert check_citations("24 days [1].", 4, True) == (True, [1], "")
    ok, cited, problem = check_citations("24 days [7].", 4, True)
    assert not ok and cited == [7] and "do not exist" in problem
    ok, _, problem = check_citations("24 days.", 4, True)
    assert not ok and "no citations" in problem
    assert check_citations("24 days.", 4, False)[0]


def test_no_answer_markers():
    assert is_no_answer("NO_ANSWER") and is_no_answer("  no_answer.") and is_no_answer("")
    assert not is_no_answer("Every employee gets 24 days [1].")


def test_an_answer_of_only_source_numbers_is_rejected():
    ok, _, problem = check_citations("[1]", 4, True)
    assert not ok and "only source numbers" in problem
    assert not check_citations(" [1][2]. ", 4, True)[0]


def test_greetings_are_small_talk_but_questions_are_not():
    for text in ["hi", "Hi!", "hello", "thanks", "Thank you.", "good morning", "ok"]:
        assert SMALL_TALK.match(text), text
    for text in ["hi who is balamurugan", "thanks for the leave policy, how many days?", "okay what are the password rules"]:
        assert not SMALL_TALK.match(text), text


def test_a_greeting_is_answered_without_searching(monkeypatch):
    from apps.retrieval import orchestrator

    monkeypatch.setattr(orchestrator, "live_generation", lambda: pytest.fail("a greeting must not search"))
    events = []
    assert orchestrator.answer(user=None, question="Hello!", emit=lambda name, data: events.append((name, data))) is None
    assert events[0][0] == "abstain" and events[0][1]["reason"] == "small_talk"


def test_the_contextual_header_names_the_document_and_section():
    assert document_title("Balamurugan_Thangadurai_GenAI_CV.pdf") == "Balamurugan Thangadurai GenAI CV"
    assert document_title("README") == "README"
    text = with_header("Samsung R&D ...", filename="Bala_CV.pdf", section_path="PROFESSIONAL EXPERIENCE")
    assert text == "Bala CV > PROFESSIONAL EXPERIENCE\nSamsung R&D ..."
    c = Candidate("x", chunk=SimpleNamespace(text_content="body", section_path="", document_version=SimpleNamespace(
        document=SimpleNamespace(filename="Handbook.pdf"))))  # fmt: skip
    assert rerank_text(c, contextual=False) == "body" and rerank_text(c, contextual=True) == "Handbook\nbody"


def test_bm25_fields_are_an_allow_list():
    from pydantic import ValidationError

    from apps.registry.components import RetrieveBm25

    assert RetrieveBm25(fields=["text_content", "section_path^2", "filename^1.5"], fuzziness="AUTO")
    for bad in (["password_hash"], ["text_content^x"], []):
        with pytest.raises(ValidationError):
            RetrieveBm25(fields=bad)


def test_bm25_keeps_the_old_query_for_old_versions_and_searches_titles_for_new_ones(monkeypatch):
    from apps.core.clients import search_index

    bodies = []
    fake = SimpleNamespace(search=lambda index, body: bodies.append(body) or {"hits": {"hits": []}})
    monkeypatch.setattr(search_index, "client", lambda: fake)
    search_index.search("i", "leave", generation_id="g", access_groups=["general"], size=5)
    search_index.search("i", "leave", generation_id="g", access_groups=["general"], size=5,
                        fields=["text_content", "filename"], fuzziness="AUTO")  # fmt: skip
    assert bodies[0]["query"]["bool"]["must"] == {"match": {"text_content": {"query": "leave"}}}
    multi = bodies[1]["query"]["bool"]["must"]["multi_match"]
    assert multi["fields"] == ["text_content", "filename"] and multi["fuzziness"] == "AUTO"
    assert bodies[1]["query"]["bool"]["filter"][1] == {"terms": {"access_groups": ["general"]}}  # the access filter stays


def test_the_context_window_is_sent_to_ollama(monkeypatch):
    from apps.core.clients import llm

    seen = {}

    def completion(**kwargs):
        seen.update(kwargs)
        return iter([])

    monkeypatch.setattr(llm, "_litellm", lambda: SimpleNamespace(completion=completion))
    assert llm.complete("ollama/qwen2.5:3b", "hi", temperature=0, max_tokens=10, timeout=5, num_ctx=4096) == ""
    assert seen["num_ctx"] == 4096
