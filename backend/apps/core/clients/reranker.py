"""Local cross-encoder reranker (ms-marco-MiniLM-L6-v2), loaded once per process, CPU only."""

from functools import lru_cache

from django.conf import settings


@lru_cache(maxsize=1)
def model():
    import torch
    from sentence_transformers import CrossEncoder

    torch.set_num_threads(settings.TORCH_THREADS)
    return CrossEncoder(settings.RERANKER_MODEL_DIR, device="cpu", local_files_only=True)


def score(question: str, passages: list[str]) -> list[float]:
    """Higher is more relevant (raw logits: about +9 for a clear match, about -11 for an unrelated passage)."""
    if not passages:
        return []
    return [float(s) for s in model().predict([(question, passage) for passage in passages], batch_size=16)]
