FROM python:3.14-slim as base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# system dependencies for building some Python packages and for psycopg2
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev gcc netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

FROM base as production

COPY . /app

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENV DJANGO_SETTINGS_MODULE=main.settings

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["gunicorn", "main.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
