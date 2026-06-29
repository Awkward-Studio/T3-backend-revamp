#!/usr/bin/env bash
set -euo pipefail

cd workflow_manager

python manage.py migrate --noinput
python manage.py seed_roles
python manage.py seed_default_users
RESET_ADMIN_PASSWORD=${RESET_ADMIN_PASSWORD:-1} python manage.py ensure_admin

exec gunicorn workflow_manager.wsgi:application --bind 0.0.0.0:${PORT:-8000}
