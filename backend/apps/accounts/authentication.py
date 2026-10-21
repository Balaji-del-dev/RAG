from rest_framework import authentication


class SessionAuthentication(authentication.SessionAuthentication):
    """DRF session auth that answers 401 (not 403) when nobody is signed in."""

    def authenticate_header(self, request) -> str:
        return 'Session realm="api"'
