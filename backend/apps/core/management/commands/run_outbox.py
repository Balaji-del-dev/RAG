import signal
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.core.outbox import dispatch_batch


class Command(BaseCommand):
    help = "Run the outbox dispatcher: publish pending outbox_events rows to Celery until stopped."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Dispatch one batch and exit.")
        parser.add_argument("--idle-sleep", type=float, default=1.0, help="Seconds to wait when nothing is due.")

    def handle(self, *args, once: bool, idle_sleep: float, **options):
        stopping = False

        def stop(signum, frame):
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)

        if once:
            self.stdout.write(f"dispatched {dispatch_batch()}")
            return

        self.stdout.write("outbox dispatcher running (Ctrl+C to stop)")
        while not stopping:
            close_old_connections()
            if dispatch_batch() == 0:
                time.sleep(idle_sleep)
        self.stdout.write("outbox dispatcher stopped")
