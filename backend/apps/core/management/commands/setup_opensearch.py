"""Phase 0: create the OpenSearch service user that may only use the platform's rag_chunks_* indexes.

The admin login is read from the environment only and never stored:

    OPENSEARCH_ADMIN_USER=admin OPENSEARCH_ADMIN_PASSWORD=... python manage.py setup_opensearch
"""

import os

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

ROLE = "rag_app_role"
INDEX_PATTERN = "rag_chunks_*"


class Command(BaseCommand):
    help = "Create (or update) the OpenSearch role and service user for the platform."

    def handle(self, *args, **options):
        admin_user = os.environ.get("OPENSEARCH_ADMIN_USER", "admin")
        admin_password = os.environ.get("OPENSEARCH_ADMIN_PASSWORD")
        if not admin_password:
            raise CommandError("Set OPENSEARCH_ADMIN_PASSWORD in the environment (it is not stored).")
        user, password = settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD
        if not user or len(password) < 16:
            raise CommandError("Set OPENSEARCH_USER and OPENSEARCH_PASSWORD (16+ characters) in backend/.env first.")

        api = httpx.Client(
            base_url=f"{settings.OPENSEARCH_URL}/_plugins/_security/api",
            auth=(admin_user, admin_password),
            verify=settings.OPENSEARCH_CA_CERT or False,
            timeout=15,
        )

        def put(path: str, body: dict) -> None:
            response = api.put(path, json=body)
            if response.status_code not in (200, 201):
                raise CommandError(f"PUT {path} failed: {response.status_code} {response.text[:300]}")
            self.stdout.write(f"{path}: {response.json().get('status', 'OK')}")

        put(
            f"/roles/{ROLE}",
            {
                "description": "RAG platform: only its own rag_chunks_* indexes",
                "cluster_permissions": ["cluster_monitor", "cluster_composite_ops"],
                "index_permissions": [{"index_patterns": [INDEX_PATTERN], "allowed_actions": ["indices_all"]}],
            },
        )
        put(f"/internalusers/{user}", {"password": password, "description": "RAG platform service user"})
        put(f"/rolesmapping/{ROLE}", {"users": [user]})
        self.stdout.write(self.style.SUCCESS(f"OpenSearch is ready: user {user} may use {INDEX_PATTERN} only."))
