#!/bin/bash
set -e
cd "$(dirname "$0")"
pip install -q -r requirements.txt 2>/dev/null || true
python -c "from app import app; import uvicorn; uvicorn.run(app, host='0.0.0.0', port=8080)" &
sleep 1
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/
