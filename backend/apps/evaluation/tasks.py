from celery import shared_task

from . import services


@shared_task(name="evaluation.run_evaluation", soft_time_limit=6 * 3600, time_limit=6 * 3600 + 300)
def run_evaluation(run_id: str, **_) -> str:
    """Started by the evaluation.run outbox event. Slow on the CPU: several LLM calls per case."""
    return services.execute(run_id).status
