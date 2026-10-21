from django.http import JsonResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .health import check_all


class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes: list = []

    @extend_schema(summary="Up / down status of every backing service")
    def get(self, request):
        services = check_all()
        healthy = all(state == "up" for state in services.values())
        return Response(
            {"status": "ok" if healthy else "degraded", "services": services},
            status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def csrf_failure(request, reason=""):
    """CSRF_FAILURE_VIEW: the standard error shape instead of Django's HTML page."""
    return JsonResponse(
        {
            "error": {
                "code": "csrf_failed",
                "message": "Your browser did not send a valid security token. Reload the page and try again.",
                "details": {},
            },
            "request_id": getattr(request, "request_id", None),
        },
        status=403,
    )
