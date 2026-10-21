"""Small HTTP helper shared by the service clients' ping() checks."""

import httpx
from django.conf import settings


def get(url: str, **kwargs) -> httpx.Response:
    kwargs.setdefault("timeout", settings.HEALTH_CHECK_TIMEOUT)
    return httpx.get(url, **kwargs)
