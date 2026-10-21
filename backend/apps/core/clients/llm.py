"""LiteLLM -> Ollama on this machine. Streaming and one-shot completions with timeouts."""

from collections.abc import Iterator
from dataclasses import dataclass, field

from django.conf import settings

from . import http


class LLMUnavailableError(Exception):
    """Ollama did not answer (down, timed out, or the model is not pulled)."""


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    extra: dict = field(default_factory=dict)


def ping() -> bool:
    return http.get(f"{settings.OLLAMA_API_BASE}/api/tags").status_code == 200


def _litellm():
    import litellm

    litellm.suppress_debug_info = True
    litellm.drop_params = True
    return litellm


def stream(
    model: str,
    prompt: str,
    *,
    temperature: float,
    max_tokens: int,
    timeout: int,
    num_ctx: int | None = None,
    usage: Usage | None = None,
) -> Iterator[str]:
    """Yield text pieces as the model writes them. `num_ctx` is Ollama's context window (prompt + answer)."""
    extra = {"num_ctx": num_ctx} if num_ctx else {}
    try:
        response = _litellm().completion(
            model=model,
            api_base=settings.OLLAMA_API_BASE,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            stream_options={"include_usage": True},
            **extra,
        )
        for chunk in response:
            if usage is not None and getattr(chunk, "usage", None):
                usage.prompt_tokens = int(chunk.usage.prompt_tokens or 0)
                usage.completion_tokens = int(chunk.usage.completion_tokens or 0)
            if chunk.choices:
                piece = chunk.choices[0].delta.content or ""
                if piece:
                    yield piece
    except Exception as exc:
        raise LLMUnavailableError(f"{type(exc).__name__}: {exc}") from exc


def complete(
    model: str,
    prompt: str,
    *,
    temperature: float,
    max_tokens: int,
    timeout: int,
    num_ctx: int | None = None,
    usage: Usage | None = None,
) -> str:
    return "".join(
        stream(model, prompt, temperature=temperature, max_tokens=max_tokens, timeout=timeout, num_ctx=num_ctx, usage=usage)
    )
