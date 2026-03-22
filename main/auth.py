"""Bearer token authentication for paired-instance API endpoints."""

import hmac
import logging

from django.http import JsonResponse
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)


class _ApiUser:
    """Sentinel user for M2M API authentication (no real Django user)."""

    is_authenticated = True
    is_active = True


class BearerTokenAuthentication(BaseAuthentication):
    """DRF authentication backend that validates Bearer tokens against PairedInstance keys.

    On success, sets ``request.user`` to an ``_ApiUser`` sentinel and
    ``request.auth`` to the matched :class:`~config.models.PairedInstance`.
    """

    def authenticate(self, request):
        from config.models import PairedInstance

        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer "):
            return None  # No Bearer header → let other authenticators try

        key = auth[len("Bearer ") :]
        for pi in PairedInstance.objects.all():
            if hmac.compare_digest(key, pi.our_key):
                return (_ApiUser(), pi)

        raise AuthenticationFailed("Invalid Bearer token.")

    def authenticate_header(self, request):
        return "Bearer"


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
