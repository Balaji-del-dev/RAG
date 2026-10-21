"""Back up the two sources of truth to ~/rag-data/backups (docs/plan/03-database.md §14).

    python manage.py backup            # PostgreSQL dump (keeps the last 14) + MinIO buckets (only new or changed files)

Qdrant and OpenSearch are not backed up: they are rebuilt from the canonical chunks in PostgreSQL.
Copy the backups folder to an external disk every week.
"""

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.clients import storage

KEEP_DUMPS = 14


class Command(BaseCommand):
    help = "Back up PostgreSQL (pg_dump) and the MinIO buckets to ~/rag-data/backups."

    def add_arguments(self, parser):
        parser.add_argument("--target", default=str(Path.home() / "rag-data" / "backups"))
        parser.add_argument("--skip-files", action="store_true", help="Only dump PostgreSQL.")

    def handle(self, *args, target: str, skip_files: bool, **options):
        root = Path(target)
        self.dump_postgres(root / "pg")
        if not skip_files:
            for bucket in (settings.S3_BUCKET_ORIGINALS, settings.S3_BUCKET_ARTIFACTS, settings.S3_BUCKET_EXPORTS):
                self.mirror_bucket(bucket, root / "minio" / bucket)
        self.stdout.write(self.style.SUCCESS(f"Backup done: {root}"))

    def dump_postgres(self, folder: Path) -> None:
        if not shutil.which("pg_dump"):
            raise CommandError("pg_dump is not installed.")
        db = settings.DATABASES["default"]
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{db['NAME']}-{datetime.now():%Y%m%d-%H%M%S}.dump"
        env = {**os.environ, "PGPASSWORD": db["PASSWORD"]}
        command = ["pg_dump", "-Fc", "-h", db["HOST"], "-p", str(db["PORT"]), "-U", db["USER"], "-f", str(path), db["NAME"]]
        result = subprocess.run(command, env=env, capture_output=True, text=True, check=False)  # noqa: S603
        if result.returncode != 0:
            raise CommandError(f"pg_dump failed: {result.stderr.strip()}")
        dumps = sorted(folder.glob(f"{db['NAME']}-*.dump"))
        for old in dumps[:-KEEP_DUMPS]:
            old.unlink()
        kept = min(len(dumps), KEEP_DUMPS)
        self.stdout.write(f"PostgreSQL: {path.name} ({path.stat().st_size // 1024} KB), keeping {kept} dumps")

    def mirror_bucket(self, bucket: str, folder: Path) -> None:
        client = storage.client()
        copied = skipped = 0
        for obj in client.list_objects(bucket, recursive=True):
            local = folder / obj.object_name
            if local.exists() and local.stat().st_size == obj.size:
                skipped += 1
                continue
            local.parent.mkdir(parents=True, exist_ok=True)
            client.fget_object(bucket, obj.object_name, str(local))
            copied += 1
        host = urlparse(settings.S3_ENDPOINT_URL).netloc
        self.stdout.write(f"MinIO {host}/{bucket}: {copied} copied, {skipped} unchanged")
