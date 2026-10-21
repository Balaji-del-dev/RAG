from django.http import JsonResponse


def lockout_response(request, original_response=None, credentials=None) -> JsonResponse:
    """django-axes calls this when a username is locked out (AXES_LOCKOUT_CALLABLE)."""
    return JsonResponse(
        {
            "error": {
                "code": "account_locked",
                "message": "Too many failed sign-ins. Try again in 15 minutes or ask an admin to unlock the account.",
                "details": {},
            },
            "request_id": getattr(request, "request_id", None),
        },
        status=423,
    )
