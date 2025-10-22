#!/bin/sh
set -e

# If DATABASE_HOST is set we wait for it to be reachable
DB_HOST=${DATABASE_HOST:-db}
DB_PORT=${DATABASE_PORT:-5432}

if [ -n "$DB_HOST" ]; then
  echo "Waiting for database $DB_HOST:$DB_PORT..."
  # wait until available (nc from netcat-openbsd)
  until nc -z "$DB_HOST" "$DB_PORT"; do
    sleep 1
  done
fi

# Apply DB migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Collect static files (non-fatal)
echo "Collecting static files..."
python manage.py collectstatic --noinput || true

# Execute the container CMD
exec "$@"

