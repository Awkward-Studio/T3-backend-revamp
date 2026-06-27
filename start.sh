#!/usr/bin/env bash
set -euo pipefail

cd workflow_manager

python manage.py migrate --noinput

exec gunicorn workflow_manager.wsgi:application --bind 0.0.0.0:${PORT:-8000}
