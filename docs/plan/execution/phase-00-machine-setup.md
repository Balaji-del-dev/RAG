# Phase 0: Machine setup

## Goal

Every service and model needed by the platform runs on this machine:
- on `127.0.0.1` only;
- CPU only;
- with nothing downloaded at runtime.

## Before you start

- Read [dependency.txt](../../../dependency.txt). It lists what is already installed and what is missing.
- About 15 GB of free disk space for models, indexes and backups. 173 GB are free.

## Tasks

### System packages and runtimes
- [ ] `sudo apt install python3.12-venv python3.12-dev build-essential libmagic1 tesseract-ocr-tam tesseract-ocr-hin libgl1 libglib2.0-0`
- [ ] Node.js 24 LTS: `nvm install 24 && nvm alias default 24`. Check with `node -v`, which should print `v24.x`.
- [ ] Python environment at the repository root:
      `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- [ ] Check that PyTorch is the CPU build:
      `.venv/bin/python -c "import torch; print(torch.__version__, torch.cuda.is_available())"`
      It should print `2.14.1+cpu False`.

### Data folder (outside the repository)
- [ ] Create `~/rag-data/` with these subfolders:
  - `minio/`, `qdrant/`, `opensearch/`
  - `models/`
  - `backups/pg/`, `backups/minio/`
  - `logs/`

### PostgreSQL (installed, 16.15)
- [ ] Create the role and database:
      `CREATE ROLE rag_app LOGIN CREATEDB PASSWORD '…';`
      `CREATE DATABASE rag_platform OWNER rag_app;`
- [ ] `listen_addresses = 'localhost'`, and `scram-sha-256` in `pg_hba.conf`.

### Redis (installed, 7.0.15)
- [ ] `bind 127.0.0.1`
- [ ] `requirepass …`
- [ ] `maxmemory 256mb` and `maxmemory-policy volatile-lru`

### MinIO (installed at `~/go/bin/minio`)
- [ ] Start it:
      `minio server ~/rag-data/minio --address 127.0.0.1:9000 --console-address 127.0.0.1:9001`
- [ ] Create the buckets `rag-originals`, `rag-artifacts` and `rag-exports`, all with **versioning on**. Use `mc`.
- [ ] Create the app user `rag-app` with a policy limited to those three buckets.

### Qdrant 1.19.2 (not installed)
- [ ] Download `qdrant-x86_64-unknown-linux-gnu.tar.gz` from the Qdrant GitHub releases into its own new folder, then extract it.
- [ ] Config:
  - `service.host: 127.0.0.1`
  - `service.api_key: …`
  - `storage.storage_path: ~/rag-data/qdrant`

### OpenSearch 3.9.0 (not installed)
- [ ] Download `opensearch-3.9.0-linux-x64.tar.gz` into its own new folder, then extract it. It includes its own Java runtime.
- [ ] `opensearch.yml`:
  - `discovery.type: single-node`
  - `network.host: 127.0.0.1`
  - `path.data: ~/rag-data/opensearch`
- [ ] `jvm.options`: `-Xms512m -Xmx512m`.
- [ ] Set the initial admin password (`OPENSEARCH_INITIAL_ADMIN_PASSWORD`).
- [ ] Create the service user `rag_app` with a role allowed only on `rag_chunks_*`.
- [ ] Recommended: `sudo sysctl -w vm.max_map_count=262144`, and add it to `/etc/sysctl.conf` so it survives a reboot.

### Ollama (installed, 0.34.0)
- [ ] Environment:
  - `OLLAMA_HOST=127.0.0.1:11434`
  - `OLLAMA_MAX_LOADED_MODELS=1`
  - `OLLAMA_NUM_PARALLEL=1`
- [ ] `qwen2.5:3b` is already pulled. Add the fallback: `ollama pull qwen2.5:1.5b`.

### Local models, downloaded once into `~/rag-data/models/`
- [ ] Embedding model: `intfloat/multilingual-e5-small`
- [ ] Reranker: `cross-encoder/ms-marco-MiniLM-L6-v2`
- [ ] Docling layout and table models: `docling-tools models download`
- [ ] spaCy model for Presidio: `python -m spacy download en_core_web_sm`
- [ ] EasyOCR weights for English, Tamil and Hindi (fetched once, then used with `gpu=False`)
- [ ] After all downloads, set `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` from here on.

### Repository
- [ ] Add to `.gitignore`: `.env`, `.venv/`, `console/dist/`, `*.log`, `celerybeat-schedule*`.

## Done when

| Check | Command | Expect |
|---|---|---|
| PostgreSQL | `pg_isready -h 127.0.0.1` | `accepting connections` |
| Redis | `redis-cli -a … ping` | `PONG` |
| MinIO | `curl -s http://127.0.0.1:9000/minio/health/live -o /dev/null -w '%{http_code}'` | `200` |
| Qdrant | `curl -s -H 'api-key: …' http://127.0.0.1:6333/readyz` | `all shards are ready` |
| OpenSearch | `curl -sk -u rag_app:… https://127.0.0.1:9200/_cluster/health` | `"status":"green"` (or `yellow`) |
| Ollama | `curl -s http://127.0.0.1:11434/api/tags` | lists `qwen2.5:3b` and `qwen2.5:1.5b` |
| Models offline | load the embedder and reranker from `~/rag-data/models/` with the network off | no download attempts |
| Nothing public | `ss -ltn` | ports 5432, 6379, 9000, 9001, 6333, 9200 and 11434 listen on `127.0.0.1` only |

- [ ] Record the free RAM with all services idle (`free -h`), for comparison in Phase 9.

## Risks and tips

- **RAM is tight.** With every service running, about 4 GB is used before Django and Celery start. Start OpenSearch with the 512 MB heap from day one.
- **MinIO is archived upstream.** Keep the installed version. The backend uses only the S3 API, so swapping the store later is a configuration change.
- **Opening downloads safely:** extract downloaded archives into their own new folder. Run their binaries directly; don't run scripts from inside that folder.
