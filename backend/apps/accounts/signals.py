"""Sign-in bookkeeping: session rows, failure counts, lock state and audit events."""

from axes.signals import user_locked_out
from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models import F
from django.dispatch import receiver
from django.utils import timezone

from apps.core import audit

from . import sessions
from .models import User


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    if request is None:
        return
    row = sessions.start(request, user)
    User.objects.filter(pk=user.pk).update(failed_login_count=0, locked_until=None)
    audit.record(
        "auth.login", actor=user, entity_type="user", entity_id=user.pk, details={"session_id": str(row.pk)}, request=request
    )


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    if request is None:
        return
    sessions.end(request)
    if user is not None:
        audit.record("auth.logout", actor=user, entity_type="user", entity_id=user.pk, request=request)


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    username = (credentials or {}).get("username") or ""
    user = User.objects.filter(username=username).first()
    if user is not None:
        User.objects.filter(pk=user.pk).update(failed_login_count=F("failed_login_count") + 1)
    audit.record(
        "auth.login_failed",
        actor=username or "unknown",
        entity_type="user",
        entity_id=user.pk if user else None,
        request=request,
    )


@receiver(user_locked_out)
def on_locked_out(sender, request, username, ip_address, **kwargs):
    user = User.objects.filter(username=username).first()
    if user is None:
        return
    User.objects.filter(pk=user.pk).update(locked_until=timezone.now() + settings.AXES_COOLOFF_TIME)
    audit.record("auth.locked", actor=username, entity_type="user", entity_id=user.pk, request=request)
