"""Seed data for 4.1 (docs/plan/03-database.md §8). Data migrations call sync_registry(apps)."""

from .components import BASELINE_STEPS, COMPONENTS, GENERATION_CONFIGS, GROUNDED_PROMPT_V1, RetrievalSettings

MODELS = [
    # name, provider, model_name, type, parameters
    ("qwen2.5:3b", "ollama", "ollama/qwen2.5:3b", "LLM", {"num_ctx": 4096}),
    ("qwen2.5:1.5b", "ollama", "ollama/qwen2.5:1.5b", "LLM", {"num_ctx": 4096}),
    (
        "multilingual-e5-small",
        "sentence-transformers",
        "intfloat/multilingual-e5-small",
        "EMBEDDING",
        {"dimension": 384, "max_tokens": 512, "query_prefix": "query: ", "passage_prefix": "passage: "},
    ),
    ("ms-marco-MiniLM-L6-v2", "sentence-transformers", "cross-encoder/ms-marco-MiniLM-L6-v2", "RERANKER", {}),
]


def sync_registry(apps, schema_editor=None) -> None:
    ComponentDefinition = apps.get_model("registry", "ComponentDefinition")
    ModelDefinition = apps.get_model("registry", "ModelDefinition")
    RetrievalDefinition = apps.get_model("registry", "RetrievalDefinition")
    GenerationDefinition = apps.get_model("registry", "GenerationDefinition")
    PipelineDefinition = apps.get_model("registry", "PipelineDefinition")
    PipelineVersion = apps.get_model("registry", "PipelineVersion")
    PipelineStep = apps.get_model("registry", "PipelineStep")

    components = {}
    for key, component in COMPONENTS.items():
        components[key], _ = ComponentDefinition.objects.update_or_create(
            name=key,
            defaults={
                "component_type": component.type,
                "implementation_key": key,
                "config_schema": component.config.model_json_schema(),
                "is_active": True,
            },
        )

    models = {}
    for name, provider, model_name, model_type, params in MODELS:
        models[name], _ = ModelDefinition.objects.update_or_create(
            name=name,
            defaults={"provider": provider, "model_name": model_name, "model_type": model_type, "parameters_json": params},
        )

    retrieval, _ = RetrievalDefinition.objects.get_or_create(name="baseline", defaults=RetrievalSettings().model_dump())
    generation, _ = GenerationDefinition.objects.get_or_create(
        name="grounded-v1",
        defaults={
            "model": models["qwen2.5:3b"],
            "prompt_template": GROUNDED_PROMPT_V1,
            **{field: cls().model_dump() for field, cls in GENERATION_CONFIGS.items()},
        },
    )

    pipeline, _ = PipelineDefinition.objects.get_or_create(
        name="default", defaults={"description": "Baseline ingestion and retrieval pipeline", "is_active": True}
    )
    if not PipelineVersion.objects.filter(pipeline=pipeline).exists():
        version = PipelineVersion.objects.create(
            pipeline=pipeline,
            version_number=1,
            status="DRAFT",
            config_json={"note": "Baseline: measure first, improve with evaluation."},
            retrieval_definition=retrieval,
            generation_definition=generation,
        )
        for order, key in enumerate(BASELINE_STEPS, start=1):
            PipelineStep.objects.create(
                pipeline_version=version,
                component=components[key],
                step_order=order,
                config_json=COMPONENTS[key].config().model_dump(),
                is_enabled=True,
            )
