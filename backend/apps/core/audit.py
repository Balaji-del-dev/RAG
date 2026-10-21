"""One way for every app to write the audit log (the model lives in apps.evaluation)."""

import uuid
from typing import Any

from django.apps import apps
from django.http import HttpRequest


def client_ip(request: HttpRequest | None) -> str | None:
    if request is None:
        return None
    return request.META.get("REMOTE_ADDR") or None


def record(
    event_type: str,
    *,
    actor: Any = None,
    entity_type: str = "",
    entity_id: uuid.UUID | None = None,
    details: dict | None = None,
    request: HttpRequest | None = None,
) -> None:
    """Append one audit event. `actor` is a user, a username string, or None (system)."""
    AuditEvent = apps.get_model("evaluation", "AuditEvent")
    actor_user = actor if getattr(actor, "pk", None) is not None else None
    if actor_user is not None:
        actor_name = actor_user.get_username()
    elif isinstance(actor, str):
        actor_name = actor
    else:
        actor_name = "system"
    AuditEvent.objects.create(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor_name[:150],
        actor_user=actor_user,
        ip_address=client_ip(request),
        details_json=details or {},
    )
