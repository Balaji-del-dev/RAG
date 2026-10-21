from apps.accounts.admin_site import register

from .models import AuditEvent, EvaluationCase, EvaluationDataset, EvaluationResult, EvaluationRun

register(EvaluationDataset, EvaluationCase, EvaluationRun, EvaluationResult)
# The audit log is append-only: a database trigger refuses every update and delete.
register(AuditEvent, read_only=True, list_display=["created_at", "actor", "event_type", "entity_type", "entity_id", "ip_address"])
