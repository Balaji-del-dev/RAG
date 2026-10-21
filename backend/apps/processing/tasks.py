from celery import Task, shared_task

from . import runner
from .components.base import TransientError


class JobTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Retries used up (or a crash outside the steps): mark the job FAILED, never leave it RETRY."""
        job_id = kwargs.get("job_id") or (args[0] if args else None)
        if job_id:
            runner.give_up(job_id, exc)


@shared_task(
    name="processing.run_job",
    base=JobTask,
    autoretry_for=(TransientError,),
    retry_backoff=10,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def run_job(job_id: str, **_) -> str:
    """Started by the job.dispatch outbox event. Safe to run twice: chunk IDs are deterministic."""
    return runner.run(job_id)
