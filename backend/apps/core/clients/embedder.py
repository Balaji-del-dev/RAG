"""Local embedding model (multilingual-e5-small), loaded once per process, CPU only, never downloaded."""

import hashlib
from functools import lru_cache
from pathlib import Path

import numpy as np
from django.conf import settings


@lru_cache(maxsize=1)
def model():
    import torch
    from sentence_transformers import SentenceTransformer

    torch.set_num_threads(settings.TORCH_THREADS)
    return SentenceTransformer(settings.EMBEDDING_MODEL_DIR, device="cpu", local_files_only=True)


@lru_cache(maxsize=1)
def tokenizer():
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(settings.EMBEDDING_MODEL_DIR, local_files_only=True)


def count_tokens(text: str) -> int:
    return len(tokenizer().encode(text, add_special_tokens=False))


@lru_cache(maxsize=1)
def model_version() -> str:
    """A stable fingerprint of the local model files (config + weights size)."""
    folder = Path(settings.EMBEDDING_MODEL_DIR)
    digest = hashlib.sha256()
    for name in ("config.json", "modules.json", "sentence_bert_config.json", "tokenizer_config.json"):
        path = folder / name
        if path.exists():
            digest.update(path.read_bytes())
    weights = folder / "model.safetensors"
    if weights.exists():
        digest.update(str(weights.stat().st_size).encode())
    return f"{folder.name}@{digest.hexdigest()[:12]}"


def dimension() -> int:
    return int(model().get_sentence_embedding_dimension())


def embed_passages(texts: list[str], *, prefix: str = "passage: ", batch_size: int = 16, normalize: bool = True) -> np.ndarray:
    vectors = model().encode(
        [prefix + text for text in texts], batch_size=batch_size, normalize_embeddings=normalize, convert_to_numpy=True
    )
    return vectors.astype(np.float32)


def embed_query(text: str, *, prefix: str = "query: ") -> np.ndarray:
    return model().encode([prefix + text], normalize_embeddings=True, convert_to_numpy=True)[0].astype(np.float32)
