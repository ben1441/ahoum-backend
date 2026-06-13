#!/usr/bin/env bash
set -euo pipefail

# Wait for Postgres to accept connections before doing anything DB-related.
if [ -n "${DATABASE_URL:-}" ]; then
  echo "Waiting for the database..."
  python - <<'PY'
import os, time, sys
import psycopg
url = os.environ["DATABASE_URL"]
for _ in range(30):
    try:
        psycopg.connect(url, connect_timeout=2).close()
        sys.exit(0)
    except Exception:
        time.sleep(1)
print("Database did not become ready in time", file=sys.stderr)
sys.exit(1)
PY
fi

# The web role runs migrations and collectstatic; workers skip this.
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "Applying migrations..."
  python manage.py migrate --noinput
  echo "Collecting static files..."
  python manage.py collectstatic --noinput
  if [ "${SEED_DEMO:-0}" = "1" ]; then
    echo "Seeding demo data..."
    python manage.py seed_demo
  fi
fi

exec "$@"
