"""POST /api/v1/ask/ — an async view that streams the answer as server-sent events.

DRF views are synchronous; under ASGI a 20-60 second answer would block every other
request. Here the orchestrator runs in a worker thread and pushes events into a queue
that this view streams out. One answer is generated at a time on this CPU.
"""

import asyncio
import json

import structlog
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.db import close_old_connections
from django.http import HttpRequest, JsonResponse, StreamingHttpResponse

from apps.accounts.permissions import needs_mfa_code

from . import orchestrator

log = structlog.get_logger(__name__)

GENERATION_SLOT = asyncio.Semaphore(1)
WAIT_FOR_SLOT_SECONDS = 180  # an answer takes 20-60 seconds on this CPU: wait for a couple of them, then give up
RATE_LIMIT_PER_MINUTE = 10


def _error(status: int, code: str, message: str, request) -> JsonResponse:
    return JsonResponse(
        {"error": {"code": code, "message": message, "details": {}}, "request_id": getattr(request, "request_id", None)},
        status=status,
    )


def _event(name: str, data: dict) -> bytes:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


def _resolve_user(request):
    user = request.user  # django-otp wraps this one (is_verified)
    return user if user.is_authenticated else None, user


def _throttled(user) -> bool:
    if settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].get("ask") is None:
        return False
    key = f"ask-rate:{user.pk}"
    added = cache.add(key, 1, timeout=60)
    return not added and cache.incr(key) > RATE_LIMIT_PER_MINUTE


async def ask(request: HttpRequest):
    if request.method != "POST":
        return _error(405, "method_not_allowed", "Use POST.", request)
    user, wrapped = await sync_to_async(_resolve_user)(request)
    if user is None:
        return _error(401, "not_authenticated", "Sign in first.", request)
    if await sync_to_async(needs_mfa_code)(wrapped):
        return _error(403, "mfa_required", "Enter your authenticator code first.", request)
    if not await sync_to_async(user.has_perm)("rag.ask"):
        return _error(403, "permission_denied", "You don't have permission to ask questions.", request)
    if await sync_to_async(_throttled)(user):
        return _error(429, "throttled", "You can ask up to 10 questions a minute. Wait a moment.", request)
    try:
        question = str(json.loads(request.body or b"{}").get("question", ""))
    except (ValueError, AttributeError):
        return _error(400, "parse_error", 'Send JSON: {"question": "…"}.', request)
    if not orchestrator.normalize(question):
        return _error(400, "validation_error", "Type a question first.", request)
    if len(question) > orchestrator.MAX_QUESTION:
        return _error(400, "validation_error", f"Questions can be at most {orchestrator.MAX_QUESTION} characters.", request)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def emit(name: str, data: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, (name, data))

    def work() -> None:
        try:
            orchestrator.answer(user=user, question=question, emit=emit)
        except orchestrator.QuestionError as exc:
            emit("error", {"code": "validation_error", "message": str(exc)})
        except Exception as exc:
            log.exception("ask.failed")
            emit(
                "error",
                {"code": "service_unavailable", "message": f"Something went wrong while answering ({type(exc).__name__})."},
            )
        finally:
            close_old_connections()
            loop.call_soon_threadsafe(queue.put_nowait, None)
            # Free the slot only when the model is free: also when the browser left in the middle of the answer.
            loop.call_soon_threadsafe(GENERATION_SLOT.release)

    async def events():
        if GENERATION_SLOT.locked():
            yield _event("status", {"stage": "waiting"})
        try:
            await asyncio.wait_for(GENERATION_SLOT.acquire(), timeout=WAIT_FOR_SLOT_SECONDS)
        except TimeoutError:
            busy = "Other answers are still being written. Try again in a minute."
            yield _event("error", {"code": "llm_busy", "message": busy})
            return
        try:
            loop.run_in_executor(None, work)  # the thread releases the slot when it ends
        except BaseException:
            GENERATION_SLOT.release()
            raise
        yield _event("status", {"stage": "queued"})
        while True:
            item = await queue.get()
            if item is None:
                break
            yield _event(*item)

    response = StreamingHttpResponse(events(), content_type="text/event-stream; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
