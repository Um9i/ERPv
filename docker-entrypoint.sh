#!/bin/sh
set -e

# Wait for DB to be available
DB_HOST=${DB_HOST:-db}
DB_PORT=${DB_PORT:-5432}

echo "Waiting for database at $DB_HOST:$DB_PORT..."
while ! python -c "import socket; socket.create_connection(('$DB_HOST', $DB_PORT), timeout=2)" 2>/dev/null; do
  sleep 1
done

# Collect static files into the shared volume
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Apply database migrations
echo "Running migrations..."
python manage.py migrate --noinput

exec "$@"
