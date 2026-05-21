#!/usr/bin/env bash
set -euo pipefail

cd workflow_manager

python manage.py makemigrations --noinput
python manage.py migrate --noinput
python manage.py seed_roles
python manage.py ensure_admin
