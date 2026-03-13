"""Bearer token authentication for paired-instance API endpoints."""

import hmac
import logging

from django.http import JsonResponse

logger = logging.getLogger(__name__)


def verify_bearer_token(request, *, log_prefix="api"):
    """Validate a Bearer token against all PairedInstance keys.

    Returns ``None`` on success, or a :class:`JsonResponse` with a 401 status
    that the caller should return immediately.
    """
    from config.models import PairedInstance

    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth.startswith("Bearer "):
        logger.warning("%s_auth_failed", log_prefix, extra={"reason": "missing_bearer"})
        return JsonResponse({"error": "Unauthorized"}, status=401)
    key = auth[len("Bearer ") :]
    if not any(
        hmac.compare_digest(key, pi.our_key) for pi in PairedInstance.objects.all()
    ):
        logger.warning("%s_auth_failed", log_prefix, extra={"reason": "invalid_key"})
        return JsonResponse({"error": "Unauthorized"}, status=401)
    return None
