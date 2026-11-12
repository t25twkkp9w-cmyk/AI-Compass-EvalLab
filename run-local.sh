#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then echo 'Run ./setup.sh first.'; exit 1; fi
if [ ! -f frontend/out/index.html ]; then npm --prefix frontend run build; fi
exec .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port "${PORT:-8200}"
