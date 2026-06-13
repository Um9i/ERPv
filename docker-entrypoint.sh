#!/bin/sh
set -e

# Wait for DB to be available (safety net if started outside compose)
DB_HOST=${DB_HOST:-db}
DB_PORT=${DB_PORT:-5432}
RETRIES=30

echo "Waiting for database at $DB_HOST:$DB_PORT..."
until python -c "import socket; socket.create_connection(('$DB_HOST', $DB_PORT), timeout=2)" 2>/dev/null; do
  RETRIES=$((RETRIES - 1))
  if [ "$RETRIES" -le 0 ]; then
    echo "ERROR: database not reachable after 30 attempts"
    exit 1
  fi
  sleep 1
done

# Collect static files into the shared volume
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Apply database migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Create default superuser if credentials are provided and user doesn't exist
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists():
    User.objects.create_superuser(
        username='$DJANGO_SUPERUSER_USERNAME',
        email='${DJANGO_SUPERUSER_EMAIL:-}',
        password='$DJANGO_SUPERUSER_PASSWORD',
    )
    print('Superuser created: $DJANGO_SUPERUSER_USERNAME')
else:
    print('Superuser already exists: $DJANGO_SUPERUSER_USERNAME')
"
fi

exec "$@"
