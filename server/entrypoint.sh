#!/bin/sh
set -e
# Only the web container migrates and seeds; workers just wait for the schema.
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  python manage.py migrate --noinput
  if [ "${SEED_DEMO:-0}" = "1" ]; then
    python manage.py seed_demo
  fi
fi
exec "$@"
