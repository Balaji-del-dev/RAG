"""Datasets, evaluation runs, metrics, gates against the baseline, and four-eyes release approval."""

import csv
import io
import json
import re
from statistics import mean

import structlog
from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import AccessGroup, Role, User, UserAccessGroup, UserRole
from apps.core import audit, outbox
from apps.core.clients import storage
from apps.core.exceptions import Conflict
from apps.indexing import services as indexing
from apps.indexing.models import IndexGeneration
from apps.registry.models import PipelineVersion
from apps.retrieval import orchestrator
from apps.retrieval.models import FailureCase, RetrievalResult

from .models import EvaluationCase, EvaluationDataset, EvaluationResult, EvaluationRun

log = structlog.get_logger(__name__)

SERVICE_ACCOUNT = "svc-evaluation"
WORD = re.compile(r"[^\W_]{3,}", re.UNICODE)
STOP = {
    "the",
    "and",
    "for",
    "are",
    "with",
    "that",
    "this",
    "from",
    "per",
    "you",
    "your",
    "can",
    "may",
    "has",
    "have",
    "was",
    "will",
}


# ---------------------------------------------------------------- datasets


def is_frozen(dataset: EvaluationDataset) -> bool:
    return dataset.runs.exists()


def require_editable(dataset: EvaluationDataset) -> None:
    if is_frozen(dataset):
        raise Conflict(
            "This dataset version was used by a run and is frozen. Create a new version to change it.", code="dataset_frozen"
        )


def create_dataset(*, name: str, description: str, by, request=None) -> EvaluationDataset:
    if EvaluationDataset.objects.filter(name=name).exists():
        raise ValidationError({"name": ["A dataset with this name exists. Create a new version of it instead."]})
    dataset = EvaluationDataset.objects.create(name=name, version=1, description=description or None)
    audit.record("dataset.created", actor=by, entity_type="evaluation_dataset", entity_id=dataset.pk, request=request)
    return dataset


@transaction.atomic
def new_version(dataset: EvaluationDataset, *, by, extra_cases: list[dict] | None = None, request=None) -> EvaluationDataset:
    number = EvaluationDataset.objects.filter(name=dataset.name).aggregate(n=Max("version"))["n"] + 1
    copy = EvaluationDataset.objects.create(name=dataset.name, version=number, description=dataset.description)
    EvaluationCase.objects.bulk_create(
        EvaluationCase(
            dataset=copy,
            question=c.question,
            expected_answer=c.expected_answer,
            expected_sources=c.expected_sources,
            case_type=c.case_type,
            metadata_json=c.metadata_json,
        )  # fmt: skip
        for c in dataset.cases.all()
    )
    for case in extra_cases or []:
        EvaluationCase.objects.create(dataset=copy, **case)
    audit.record("dataset.versioned", actor=by, entity_type="evaluation_dataset", entity_id=copy.pk, request=request,
                 details={"from_version": dataset.version, "version": number, "added": len(extra_cases or [])})  # fmt: skip
    return copy


def version_from_failures(dataset: EvaluationDataset, *, by, request=None) -> EvaluationDataset:
    """A new dataset version that also contains every resolved failure case's question."""
    existing = set(dataset.cases.values_list("question", flat=True))
    extra = [
        {"question": f.retrieval_run.query_text, "expected_answer": None, "expected_sources": [], "case_type": "FACTUAL",
         "metadata_json": {"from_failure_case": str(f.pk), "failure_type": f.failure_type, "notes": f.resolution_notes or ""}}
        for f in FailureCase.objects.filter(review_status=FailureCase.Review.RESOLVED).select_related("retrieval_run")
        if f.retrieval_run.query_text not in existing
    ]  # fmt: skip
    if not extra:
        raise Conflict("No resolved failure cases are missing from this dataset.", code="nothing_to_add")
    return new_version(dataset, by=by, extra_cases=extra, request=request)


def _split_sources(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def parse_cases(filename: str, data: bytes) -> list[dict]:
    """CSV (question, expected_answer, expected_sources ';'-separated, case_type, as_groups) or a JSON list of the same keys."""
    text = data.decode("utf-8-sig")
    rows = json.loads(text) if filename.lower().endswith(".json") else list(csv.DictReader(io.StringIO(text)))
    if not isinstance(rows, list):
        raise ValidationError({"file": ["JSON must be a list of cases."]})
    cases, errors = [], {}
    valid_types = set(EvaluationCase.Type.values)
    for number, row in enumerate(rows, start=1):
        question = str(row.get("question") or "").strip()
        case_type = str(row.get("case_type") or "FACTUAL").strip().upper()
        if not question:
            errors[f"row {number}"] = ["question is empty"]
            continue
        if case_type not in valid_types:
            errors[f"row {number}"] = [f"case_type must be one of {sorted(valid_types)}"]
            continue
        metadata = {"as_groups": _split_sources(row.get("as_groups"))} if row.get("as_groups") else {}
        cases.append({
            "question": question,
            "expected_answer": (str(row.get("expected_answer") or "").strip() or None),
            "expected_sources": _split_sources(row.get("expected_sources")),
            "case_type": case_type,
            "metadata_json": metadata,
        })  # fmt: skip
    if errors:
        raise ValidationError(errors)
    if not cases:
        raise ValidationError({"file": ["The file has no cases."]})
    return cases


# ---------------------------------------------------------------- runs


def service_account() -> User:
    """The evaluation service account: no password (cannot sign in), Evaluator, member of every access group."""
    user, created = User.objects.get_or_create(
        username=SERVICE_ACCOUNT, defaults={"email": f"{SERVICE_ACCOUNT}@localhost", "display_name": "Evaluation service account"}
    )
    if created or user.has_usable_password():
        user.set_unusable_password()
        user.save(update_fields=["password"])
    for name in (Role.USER, Role.EVALUATOR):
        UserRole.objects.get_or_create(user=user, role=Role.objects.get(name=name))
    have = set(user.user_access_groups.values_list("access_group_id", flat=True))
    UserAccessGroup.objects.bulk_create(
        UserAccessGroup(user=user, access_group=g) for g in AccessGroup.objects.exclude(pk__in=have)
    )
    return User.objects.get(pk=user.pk)


@transaction.atomic
def start_run(
    *,
    dataset: EvaluationDataset,
    pipeline_version: PipelineVersion,
    generation: IndexGeneration,
    use_llm_judge: bool,
    by,
    request=None,
):
    if generation.pipeline_version_id != pipeline_version.pk:
        raise ValidationError({"index_generation_id": ["This generation belongs to another pipeline version."]})
    if generation.status in (IndexGeneration.Status.FAILED, IndexGeneration.Status.RETIRED):
        raise ValidationError({"index_generation_id": ["Choose a live, building or validating generation."]})
    if not dataset.cases.exists():
        raise ValidationError({"dataset_id": ["The dataset has no cases."]})
    run = EvaluationRun.objects.create(
        dataset=dataset, pipeline_version=pipeline_version, index_generation=generation,
        summary_json={"use_llm_judge": use_llm_judge, "started_by": by.username, "cases": dataset.cases.count()},
    )  # fmt: skip
    outbox.emit("evaluation.run", run, {"run_id": str(run.pk)})
    audit.record("evaluation_run.started", actor=by, entity_type="evaluation_run", entity_id=run.pk, request=request,
                 details={"dataset": str(dataset), "pipeline_version": pipeline_version.version_number})  # fmt: skip
    return run


def _keywords(text: str) -> set[str]:
    return {w.lower() for w in WORD.findall(text or "") if w.lower() not in STOP}


def _matches(result_doc: tuple[str, str], expected: list[str]) -> bool:
    doc_id, filename = result_doc
    wanted = {e.lower() for e in expected}
    return doc_id.lower() in wanted or filename.lower() in wanted


def score_case(
    case: EvaluationCase, run_id, final: tuple[str, dict] | None, context_texts: list[str]
) -> dict[str, tuple[float, dict]]:
    """Deterministic metrics for one case: retrieval, answer keywords, abstention, access."""
    metrics: dict[str, tuple[float, dict]] = {}
    event, data = final or ("error", {})
    answered = event == "done"
    ranked = list(
        RetrievalResult.objects.filter(retrieval_run_id=run_id)
        .order_by("fusion_rank")
        .values_list("chunk__document_version__document_id", "chunk__document_version__document__filename")
    )
    docs_in_order: list[tuple[str, str]] = []
    for doc_id, filename in ranked:
        if (str(doc_id), filename) not in docs_in_order:
            docs_in_order.append((str(doc_id), filename))
    expected = case.expected_sources or []

    if case.case_type == EvaluationCase.Type.ACCESS:
        leaked = [d for d in docs_in_order if _matches(d, expected)]
        metrics["access_safe"] = (
            0.0 if leaked else 1.0,
            {"leaked": [f for _, f in leaked], "as_groups": case.metadata_json.get("as_groups")},
        )
        return metrics
    if case.case_type == EvaluationCase.Type.NO_ANSWER:
        metrics["abstention_correct"] = (0.0 if answered else 1.0, {"outcome": event})
        return metrics
    if expected:
        top5 = docs_in_order[:5]
        found = [e for e in expected if any(_matches(d, [e]) for d in top5)]
        first = next((rank for rank, d in enumerate(docs_in_order, start=1) if _matches(d, expected)), None)
        metrics["hit@5"] = (1.0 if found else 0.0, {"top5": [f for _, f in top5]})
        metrics["recall@5"] = (len(found) / len(expected), {"found": found, "expected": expected})
        metrics["mrr"] = (1.0 / first if first else 0.0, {"first_relevant_rank": first})
    if case.expected_answer:
        wanted = _keywords(case.expected_answer)
        got = _keywords(data.get("answer", "")) if answered else set()
        recall = len(wanted & got) / len(wanted) if wanted else 0.0
        metrics["answer_keyword_recall"] = (recall, {"missing": sorted(wanted - got)[:20], "outcome": event})
    return metrics


def execute(run_id: str) -> EvaluationRun:
    run = EvaluationRun.objects.select_related(
        "dataset", "pipeline_version__generation_definition__model", "index_generation"
    ).get(pk=run_id)
    if run.status not in (EvaluationRun.Status.QUEUED, EvaluationRun.Status.ERROR):
        return run
    EvaluationRun.objects.filter(pk=run.pk).update(status=EvaluationRun.Status.RUNNING, started_at=timezone.now())
    use_judge = bool(run.summary_json.get("use_llm_judge"))
    judge_model = run.pipeline_version.generation_definition.model.model_name
    account = service_account()
    EvaluationResult.objects.filter(evaluation_run=run).delete()
    try:
        for case in run.dataset.cases.order_by("id"):
            collected: dict = {"final": None, "context": []}

            def emit(name, data, collected=collected):
                if name in ("done", "abstain", "error"):
                    collected["final"] = (name, data)

            retrieval_run = orchestrator.answer(
                user=account, question=case.question, emit=emit, generation=run.index_generation,
                scope=case.metadata_json.get("as_groups") or None,
                on_context=lambda ctx, collected=collected: collected.__setitem__("context", [c.chunk.text_content for c in ctx]),
            )  # fmt: skip
            metrics = score_case(case, retrieval_run.pk if retrieval_run else None, collected["final"], collected["context"])
            final = collected["final"] or ("error", {})
            if use_judge and final[0] == "done" and case.case_type not in ("ACCESS", "NO_ANSWER"):
                from .judge import judge_answer

                metrics.update(judge_answer(judge_model, case.question, final[1].get("answer", ""), collected["context"]))
            gates = settings.EVAL_GATES
            EvaluationResult.objects.bulk_create(
                EvaluationResult(
                    evaluation_run=run,
                    evaluation_case=case,
                    metric_name=name,
                    score=score,
                    passed=score >= gates.get(name, {}).get("min", 0.5) and not name.endswith("_error"),
                    details_json={
                        **details,
                        "retrieval_run_id": str(retrieval_run.pk) if retrieval_run else None,
                        "outcome": final[0],
                    },
                )  # fmt: skip
                for name, (score, details) in metrics.items()
            )
        summary = summarize(run)
        status = EvaluationRun.Status.PASSED if summary["passed"] else EvaluationRun.Status.FAILED
    except Exception as exc:
        log.exception("evaluation.crashed", run_id=str(run.pk))
        summary = {**run.summary_json, "error": f"{type(exc).__name__}: {exc}"[:1000]}
        status = EvaluationRun.Status.ERROR
    EvaluationRun.objects.filter(pk=run.pk).update(status=status, summary_json=summary, completed_at=timezone.now())
    run.refresh_from_db()
    try:
        storage.put_bytes(settings.S3_BUCKET_EXPORTS, f"evaluations/{run.pk}/report.json",
                          json.dumps(report(run), indent=2, default=str).encode(), "application/json")  # fmt: skip
    except Exception as exc:  # the report copy is a convenience; the database has everything
        log.warning("evaluation.report_not_saved", error=str(exc))
    return run


def baseline_for(run: EvaluationRun) -> EvaluationRun | None:
    """The latest finished run of the same dataset on the live pipeline version (not this run)."""
    live = indexing.live_generation()
    if live is None:
        return None
    return (
        EvaluationRun.objects.filter(
            dataset__name=run.dataset.name,
            pipeline_version=live.pipeline_version,
            status__in=[EvaluationRun.Status.PASSED, EvaluationRun.Status.FAILED],
        )
        .exclude(pk=run.pk)
        .order_by("-completed_at")
        .first()
    )


def metric_means(run: EvaluationRun) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for name, score in EvaluationResult.objects.filter(evaluation_run=run).values_list("metric_name", "score"):
        if not name.endswith("_error"):
            values.setdefault(name, []).append(score)
    return {name: round(mean(scores), 4) for name, scores in values.items()}


def summarize(run: EvaluationRun) -> dict:
    means = metric_means(run)
    baseline = baseline_for(run)
    base_means = metric_means(baseline) if baseline else {}
    gates = []
    for name, value in means.items():
        rule = settings.EVAL_GATES.get(name, {})
        minimum, max_drop = rule.get("min"), rule.get("max_drop")
        base = base_means.get(name)
        ok_min = minimum is None or value >= minimum
        ok_drop = max_drop is None or base is None or value >= base - max_drop
        gates.append(
            {"metric": name, "value": value, "baseline": base, "min": minimum, "max_drop": max_drop, "passed": ok_min and ok_drop}
        )
    errors = EvaluationResult.objects.filter(evaluation_run=run, metric_name__endswith="_error").count()
    return {
        **run.summary_json,
        "metrics": means,
        "baseline_run_id": str(baseline.pk) if baseline else None,
        "baseline": base_means,
        "gates": gates,
        "judge_errors": errors,
        "passed": bool(gates) and all(g["passed"] for g in gates),
    }


def report(run: EvaluationRun) -> dict:
    return {
        "run_id": str(run.pk), "dataset": str(run.dataset), "pipeline_version": run.pipeline_version.version_number,
        "generation": run.index_generation.generation_number, "status": run.status, "summary": run.summary_json,
        "results": list(
            EvaluationResult.objects.filter(evaluation_run=run).values(
                "evaluation_case__question", "metric_name", "score", "passed"
            )
        ),
    }  # fmt: skip


@transaction.atomic
def approve(run: EvaluationRun, *, by, request=None) -> EvaluationRun:
    """Four-eyes release: a passed run, approved by someone other than the version's author,
    publishes the pipeline version and its index generation together."""
    run = EvaluationRun.objects.select_for_update().select_related("pipeline_version", "index_generation").get(pk=run.pk)
    version, generation = run.pipeline_version, run.index_generation
    if run.status != EvaluationRun.Status.PASSED:
        raise Conflict("Only a run that passed all its gates can be approved.", code="run_not_passed")
    if run.approved_by_id:
        raise Conflict("This run is already approved.", code="already_approved")
    if version.created_by_id and version.created_by_id == by.pk:
        raise Conflict(
            "You can't approve your own pipeline version. Another Release approver must do it (four-eyes rule).", code="four_eyes"
        )
    if version.status == PipelineVersion.Status.PUBLISHED and generation.status == IndexGeneration.Status.PUBLISHED:
        raise Conflict("This version and generation are already live — this run is the baseline.", code="already_live")
    if not indexing.validated(generation):
        raise Conflict("Validate the index generation first; every check must pass.", code="not_validated")
    run.approved_by = by
    run.save(update_fields=["approved_by"])
    PipelineVersion.objects.filter(pipeline=version.pipeline, status=PipelineVersion.Status.PUBLISHED).exclude(
        pk=version.pk
    ).update(status=PipelineVersion.Status.RETIRED)
    if version.status != PipelineVersion.Status.PUBLISHED:
        version.status = PipelineVersion.Status.PUBLISHED
        version.published_by = by
        version.published_at = timezone.now()
        version.save(update_fields=["status", "published_by", "published_at"])
    indexing.publish(generation, by=by, request=request, approved_release=True)
    audit.record("release.approved", actor=by, entity_type="evaluation_run", entity_id=run.pk, request=request,
                 details={"pipeline_version": version.version_number, "generation": generation.generation_number})  # fmt: skip
    return run
