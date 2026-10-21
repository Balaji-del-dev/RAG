"""Celery app: Redis database 2 as broker, queues ingest · index · evaluation."""

import os

from celery import Celery
from kombu import Exchange, Queue

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

QUEUES = ("ingest", "index", "evaluation")

app = Celery("rag_platform")
app.config_from_object("django.conf:settings", namespace="CELERY")
# Each queue has its own exchange and routing key, so a task reaches exactly one queue.
app.conf.task_queues = tuple(Queue(name, Exchange(name, type="direct"), routing_key=name) for name in QUEUES)
app.conf.task_default_exchange = "ingest"
app.conf.task_default_routing_key = "ingest"
app.autodiscover_tasks()
