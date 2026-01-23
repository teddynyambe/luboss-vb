#!/bin/bash
# Start Luboss95 Village Banking v2 API server

cd "$(dirname "$0")"
source app/venv/bin/activate
uvicorn app.main:app --reload --port 8002
