# Offline Hybrid RAG Platform — Architecture

Architecture documentation for a fully local, configurable RAG platform built from:

- **Application:** Django + DRF, Celery + Redis
- **Storage:** PostgreSQL, MinIO
- **Search:** Qdrant, OpenSearch
- **Models:** LiteLLM → Ollama / vLLM
- **Quality:** Langfuse, DeepEval
- **Frontend:** React

The full write-up is in **[docs/README.md](docs/README.md)**.

| Diagram | |
|---|---|
| System architecture | [docs/images/01-system-architecture.png](docs/images/01-system-architecture.png) |
| Data & storage architecture | [docs/images/02-database-architecture.png](docs/images/02-database-architecture.png) |
| PostgreSQL schema | [docs/images/03-database-schema.png](docs/images/03-database-schema.png) |
| Ingestion & indexing flow | [docs/images/04-ingestion-flow.png](docs/images/04-ingestion-flow.png) |
| Online retrieval & generation flow | [docs/images/05-query-flow.png](docs/images/05-query-flow.png) |
| Evaluation & improvement loop | [docs/images/06-evaluation-loop.png](docs/images/06-evaluation-loop.png) |

![System architecture](docs/images/01-system-architecture.png)

The HTML sources in `docs/src/` open in any browser. Each page fits the window; scroll to zoom and drag to pan.
