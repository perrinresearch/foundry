#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${PYTHONPATH:-}:${ROOT}/backend"
export FOUNDRY_PORT="${FOUNDRY_PORT:-8000}"

UVICORN="$ROOT/venv/bin/uvicorn"
if [ -x "$UVICORN" ]; then
  exec "$UVICORN" foundry.api.app:app --host 0.0.0.0 --port "$FOUNDRY_PORT" --reload
fi

if [ -d "$ROOT/venv" ] && [ ! -x "$UVICORN" ]; then
  echo "Note: venv exists but uvicorn is not installed there." >&2
  echo "  Fix: rm -rf venv && python3 -m venv venv && venv/bin/pip install -r backend/requirements.txt" >&2
  echo "  Or use system packages (below)." >&2
fi

if python3 -m uvicorn --version >/dev/null 2>&1; then
  exec python3 -m uvicorn foundry.api.app:app --host 0.0.0.0 --port "$FOUNDRY_PORT" --reload
fi

echo "Install dependencies: pip install -r backend/requirements.txt" >&2
exit 1
