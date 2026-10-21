from django.contrib.auth import logout
from django.http import JsonResponse

from . import sessions

MESSAGES = {
    "revoked": "Your session was ended. Please sign in again.",
    "expired": "Your session has expired. Please sign in again.",
    "idle": "You were signed out after a period of inactivity.",
}


class SessionGuardMiddleware:
    """Rejects revoked, expired and idle sessions; keeps last_seen_at fresh."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            reason = sessions.problem(request)
            if reason is not None:
                logout(request)
                if request.path.startswith("/api/"):
                    return JsonResponse(
                        {
                            "error": {"code": "session_expired", "message": MESSAGES[reason], "details": {}},
                            "request_id": getattr(request, "request_id", None),
                        },
                        status=401,
                    )
        return self.get_response(request)
