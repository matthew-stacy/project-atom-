#!/usr/bin/env bash
# Start the Project ATOM pose service (used by loop.py at 127.0.0.1:8000)
set -e
cd "$(dirname "$0")"          # always run from the repo root
source .venv/bin/activate
exec uvicorn service.app:app --host 127.0.0.1 --port 8000
