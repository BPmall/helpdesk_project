#!/bin/sh
set -e
PORT="${PORT:-8000}"
echo "Starting gunicorn on 0.0.0.0:${PORT}"
exec gunicorn run:app \
  --bind "0.0.0.0:${PORT}" \
  --workers 1 \
  --timeout 120 \
  --log-level info \
  --access-logfile -
