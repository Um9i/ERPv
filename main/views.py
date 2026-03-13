"""Main app views."""

import logging

from django.db import connection
from django.http import JsonResponse
from django.views import View

logger = logging.getLogger(__name__)


class HealthCheckView(View):
    """Unauthenticated health-check endpoint for container orchestration."""

    def get(self, request):
        status: dict[str, object] = {"status": "ok"}
        checks: dict[str, str] = {}

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "error"
            status["status"] = "error"
            logger.exception("Health check: database unreachable")

        status["checks"] = checks
        code = 200 if status["status"] == "ok" else 503
        return JsonResponse(status, status=code)
