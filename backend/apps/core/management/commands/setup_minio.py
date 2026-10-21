"""Phase 0: create the three buckets (versioning on) and the bucket-limited app user in MinIO.

Run once, and again whenever the app user's secret changes. The root login is read
from the environment only and never stored:

    MINIO_ROOT_USER=... MINIO_ROOT_PASSWORD=... python manage.py setup_minio
"""

import json
import os
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from minio import Minio
from minio.commonconfig import ENABLED
from minio.credentials import StaticProvider
from minio.minioadmin import MinioAdmin
from minio.versioningconfig import VersioningConfig

POLICY_NAME = "rag-app-buckets"


def bucket_policy(buckets: list[str]) -> dict:
    """Only these buckets: list them, and read, write and delete their objects (all versions)."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["s3:GetBucketLocation", "s3:ListBucket", "s3:ListBucketVersions", "s3:GetBucketVersioning"],
                "Resource": [f"arn:aws:s3:::{b}" for b in buckets],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:GetObjectVersion",
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:DeleteObjectVersion",
                    "s3:AbortMultipartUpload",
                    "s3:ListMultipartUploadParts",
                ],
                "Resource": [f"arn:aws:s3:::{b}/*" for b in buckets],
            },
        ],
    }


class Command(BaseCommand):
    help = "Create the platform's MinIO buckets (versioned) and its bucket-limited app user."

    def handle(self, *args, **options):
        root_user, root_password = os.environ.get("MINIO_ROOT_USER"), os.environ.get("MINIO_ROOT_PASSWORD")
        if not root_user or not root_password:
            raise CommandError("Set MINIO_ROOT_USER and MINIO_ROOT_PASSWORD in the environment (they are not stored).")
        app_key, app_secret = settings.S3_ACCESS_KEY, settings.S3_SECRET_KEY
        if not app_key or len(app_secret) < 16:
            raise CommandError("Set S3_ACCESS_KEY and S3_SECRET_KEY (16+ characters) in backend/.env first.")

        endpoint = urlparse(settings.S3_ENDPOINT_URL)
        secure = endpoint.scheme == "https"
        root = Minio(endpoint.netloc, access_key=root_user, secret_key=root_password, secure=secure)
        buckets = [settings.S3_BUCKET_ORIGINALS, settings.S3_BUCKET_ARTIFACTS, settings.S3_BUCKET_EXPORTS]

        for bucket in buckets:
            if root.bucket_exists(bucket):
                self.stdout.write(f"bucket {bucket}: exists")
            else:
                root.make_bucket(bucket)
                self.stdout.write(f"bucket {bucket}: created")
            root.set_bucket_versioning(bucket, VersioningConfig(ENABLED))

        admin = MinioAdmin(endpoint=endpoint.netloc, credentials=StaticProvider(root_user, root_password), secure=secure)
        admin.policy_add(POLICY_NAME, policy=bucket_policy(buckets))
        admin.user_add(app_key, app_secret)  # creates the user, or sets a new secret
        try:
            admin.attach_policy([POLICY_NAME], user=app_key)
        except Exception as exc:  # already attached
            if "already" not in str(exc).lower():
                raise
        info = json.loads(admin.user_info(app_key))
        self.stdout.write(f"user {app_key}: status={info.get('status')} policy={info.get('policyName')}")
        self.stdout.write(self.style.SUCCESS("MinIO is ready: 3 versioned buckets and the app user."))
