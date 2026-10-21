import uuid

import structlog


class RequestIDMiddleware:
    """Give every request an ID (also used as the trace ID) and return it as X-Request-ID."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request.request_id, path=request.path)
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        return response
