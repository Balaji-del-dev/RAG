from apps.accounts.admin_site import register

from .models import OutboxEvent

# Written by the services and read by the dispatcher (clear dispatched_at to send an event again).
register(OutboxEvent)
