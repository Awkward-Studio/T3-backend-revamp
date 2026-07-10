#!/usr/bin/env bash
set -euo pipefail

cd workflow_manager

python manage.py migrate --noinput
python manage.py seed_roles
python manage.py seed_default_users
