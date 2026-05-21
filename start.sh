#!/usr/bin/env bash
set -euo pipefail

cd workflow_manager

exec gunicorn workflow_manager.wsgi:application --bind 0.0.0.0:${PORT:-8000}
