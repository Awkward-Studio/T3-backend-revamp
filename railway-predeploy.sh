#!/usr/bin/env bash
set -euo pipefail

cd workflow_manager
python nuke_db.py
# python wipe_db_if_first_run.py
python manage.py migrate --noinput
python manage.py seed_roles
python manage.py seed_default_users
