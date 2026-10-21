from datetime import timedelta

from celery import shared_task
from django.contrib.sessions.models import Session
from django.db.models import Q
from django.utils import timezone

from .models import UserSession


@shared_task(name="accounts.purge_expired_sessions")
def purge_expired_sessions(keep_days: int = 30) -> dict:
    """Daily: drop Django's expired sessions, and our session rows that ended more than keep_days ago."""
    now = timezone.now()
    django_sessions, _ = Session.objects.filter(expire_date__lt=now).delete()
    cutoff = now - timedelta(days=keep_days)
    rows, _ = UserSession.objects.filter(Q(revoked_at__lt=cutoff) | Q(expires_at__lt=cutoff)).delete()
    return {"django_sessions": django_sessions, "user_sessions": rows}
