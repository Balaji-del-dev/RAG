"""One error shape for every API error: {"error": {code, message, details}, "request_id"}."""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.views import exception_handler as drf_exception_handler


class Conflict(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The current state does not allow this action."
    default_code = "conflict"


class Locked(exceptions.APIException):
    status_code = status.HTTP_423_LOCKED
    default_detail = "Too many failed sign-ins. Try again later."
    default_code = "account_locked"


class ServiceUnavailable(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "A backing service is unavailable."
    default_code = "service_unavailable"


def _code_for(exc: Exception) -> str:
    if isinstance(exc, Http404):
        return "not_found"
    if isinstance(exc, DjangoPermissionDenied):
        return "permission_denied"
    if isinstance(exc, exceptions.ValidationError):
        return "validation_error"
    detail = getattr(exc, "detail", None)
    if isinstance(exc, exceptions.PermissionDenied) and str(detail).startswith("CSRF Failed"):
        return "csrf_failed"
    if isinstance(exc, exceptions.AuthenticationFailed):
        return "not_authenticated"
    code = getattr(detail, "code", None)  # set when raised with code="..."
    return code if isinstance(code, str) else getattr(exc, "default_code", "error")


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    request = context.get("request")
    request_id = getattr(request, "request_id", None) or getattr(getattr(request, "_request", None), "request_id", None)
    if isinstance(exc, exceptions.ValidationError):
        message = "Some fields are not valid."
        details = response.data if isinstance(response.data, dict) else {"non_field_errors": response.data}
        if isinstance(response.data, dict) and set(response.data) == {"non_field_errors"}:
            message = str(response.data["non_field_errors"][0])
    else:
        data = response.data if isinstance(response.data, dict) else {}
        message = str(data.get("detail", exc))
        details = {k: v for k, v in data.items() if k != "detail"}
    response.data = {"error": {"code": _code_for(exc), "message": message, "details": details}, "request_id": request_id}
    return response
