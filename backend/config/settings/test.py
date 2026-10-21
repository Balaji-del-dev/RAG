"""Settings for pytest: fast password hashing, local-memory cache, no real broker."""

import os

from .base import *  # noqa: F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

CELERY_BROKER_URL = "memory://"

# Tests never touch the real indexes: their own names, dropped afterwards.
INDEX_NAME_PREFIX = f"rag_chunks_test{os.getpid()}"

# django-otp waits after each wrong code; tests enter codes back to back.
OTP_TOTP_THROTTLE_FACTOR = 0

# Throttling is tested explicitly where it matters.
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {"user": None, "login": None, "ask": None}}  # noqa: F405

LOGGING = {"version": 1, "disable_existing_loggers": False}
