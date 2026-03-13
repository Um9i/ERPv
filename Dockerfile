FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# system dependencies for building some Python packages and for psycopg2
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev gcc weasyprint \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# ── TypeScript build stage ──
FROM node:22-slim AS ts-build
WORKDIR /build
COPY package.json package-lock.json tsconfig.json ./
RUN npm ci
COPY static/ts/ static/ts/
RUN npx tsc

FROM base AS production

COPY . /app
COPY --from=ts-build /build/static/js/ /app/static/js/

ENV DJANGO_SETTINGS_MODULE=main.settings

# Collect static files at build time so the manifest is baked into the image
RUN SECRETKEY=build-placeholder python manage.py collectstatic --noinput

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz/')" || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["gunicorn", "main.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
