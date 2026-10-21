"""Server-side session rows (user_sessions): create on sign-in, check on every request."""

import hashlib
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import UserSession

SESSION_ROW_KEY = "user_session_id"
LAST_SEEN_EVERY = timedelta(minutes=1)


def hash_key(session_key: str) -> str:
    return hashlib.sha256(session_key.encode()).hexdigest()


def start(request, user) -> UserSession:
    session = request.session
    if session.session_key is None:
        session.save()
    now = timezone.now()
    row = UserSession.objects.create(
        user=user,
        session_key_hash=hash_key(session.session_key),
        ip_address=request.META.get("REMOTE_ADDR") or None,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.SESSION_MAX_HOURS),
    )
    session[SESSION_ROW_KEY] = str(row.pk)
    return row


def current(request) -> UserSession | None:
    row_id = request.session.get(SESSION_ROW_KEY)
    if not row_id:
        return None
    return UserSession.objects.filter(pk=row_id).first()


def problem(request) -> str | None:
    """Why this signed-in session may not continue, or None when it is fine."""
    row = current(request)
    if row is None or row.revoked_at is not None:
        return "revoked"
    now = timezone.now()
    if row.expires_at <= now:
        return "expired"
    if now - row.last_seen_at > timedelta(minutes=settings.SESSION_IDLE_MINUTES):
        UserSession.objects.filter(pk=row.pk).update(expires_at=now)
        return "idle"
    if now - row.last_seen_at > LAST_SEEN_EVERY:
        UserSession.objects.filter(pk=row.pk).update(last_seen_at=now)
    return None


def end(request) -> None:
    row_id = request.session.get(SESSION_ROW_KEY)
    if row_id:
        UserSession.objects.filter(pk=row_id, revoked_at__isnull=True).update(revoked_at=timezone.now())
