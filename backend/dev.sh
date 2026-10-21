#!/usr/bin/env bash
# Start, stop and check the platform's own processes on this machine (CPU only, 127.0.0.1 only).
#   ./dev.sh start | stop | restart | status | logs <name>
# Each process runs as its own systemd user service (rag-api, rag-worker, …), outside VS Code, so a
# crash or restart of the editor never takes the platform down; crashed services restart by themselves.
# Logs: ~/rag-data/logs/<name>.log. The shared services (PostgreSQL, Redis, MinIO, Qdrant, OpenSearch,
# Ollama) are not touched.
set -euo pipefail

BACKEND="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$BACKEND")"
PY="$ROOT/.venv/bin"
NODE_BIN="$HOME/.nvm/versions/node/v24.22.0/bin"
LOG="$HOME/rag-data/logs"
mkdir -p "$LOG"

NAMES=(api outbox worker beat flower console)

command_for() {
  case "$1" in
    api) echo "cd '$BACKEND' && exec '$PY/uvicorn' config.asgi:application --host 127.0.0.1 --port 8001" ;;
    outbox) echo "cd '$BACKEND' && exec '$PY/python' manage.py run_outbox" ;;
    worker) echo "cd '$BACKEND' && exec '$PY/celery' -A config worker -Q ingest,index,evaluation --concurrency=1 --max-tasks-per-child=20 -n ragworker@%h -l info" ;;
    beat) echo "cd '$BACKEND' && exec '$PY/celery' -A config beat -l info --schedule '$HOME/rag-data/celerybeat-schedule'" ;;
    flower) echo "cd '$BACKEND' && exec '$PY/celery' -A config flower --address=127.0.0.1 --port=5555" ;;
    console) echo "cd '$ROOT/console' && export PATH='$NODE_BIN':/usr/bin:/bin && exec npm run dev" ;;
  esac
}

unit() { echo "rag-$1"; }
running() { systemctl --user is-active --quiet "$(unit "$1")"; }
pid_of() { systemctl --user show -p MainPID --value "$(unit "$1")" 2>/dev/null || true; }

start_one() {
  if running "$1"; then echo "$1 already running (pid $(pid_of "$1"))"; return; fi
  systemctl --user reset-failed "$(unit "$1")" 2>/dev/null || true
  systemd-run --user --quiet --unit="$(unit "$1")" --collect \
    -p Restart=on-failure -p RestartSec=5 -p TimeoutStopSec=40 -p KillMode=control-group \
    /bin/bash -c "exec >>'$LOG/$1.log' 2>&1; $(command_for "$1")"
  sleep 0.3
  echo "started $1 (pid $(pid_of "$1"))"
}

stop_one() {
  if ! running "$1"; then echo "$1 not running"; return; fi
  systemctl --user stop "$(unit "$1")"
  echo "stopped $1"
}

status() {
  for name in "${NAMES[@]}"; do
    if running "$name"; then printf "%-8s running  pid %s\n" "$name" "$(pid_of "$name")"; else printf "%-8s stopped\n" "$name"; fi
  done
  echo
  echo "console  http://localhost:5173"
  echo "api      http://127.0.0.1:8001/api/v1/health/   docs: http://127.0.0.1:8001/api/docs/"
  echo "admin    http://127.0.0.1:8001/django-admin/"
  echo "flower   http://127.0.0.1:5555"
}

case "${1:-status}" in
  start) for n in "${NAMES[@]}"; do start_one "$n"; done ;;
  stop) for n in "${NAMES[@]}"; do stop_one "$n"; done ;;
  restart) for n in "${NAMES[@]}"; do stop_one "$n"; done; for n in "${NAMES[@]}"; do start_one "$n"; done ;;
  status) status ;;
  logs) tail -n 50 -f "$LOG/${2:?usage: $0 logs api|outbox|worker|flower|console}.log" ;;
  *) echo "usage: $0 start|stop|restart|status|logs <name>" >&2; exit 2 ;;
esac
