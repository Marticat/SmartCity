#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
test -x .venv/bin/python || { echo "Create .venv and install requirements.txt; see README.md."; exit 1; }
test -f frontend/dist/index.html || { echo "Build frontend first: npm --prefix frontend ci && npm --prefix frontend run build"; exit 1; }
exec .venv/bin/python -m uvicorn backend.app.main:app --no-access-log --host 127.0.0.1 --port "${PORT:-8000}"
