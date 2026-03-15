"""Webhook dispatch – delivers event payloads to registered endpoints."""

import hashlib
import hmac
import json
import logging
import time
from typing import Any

import httpx
from django.utils import timezone

from .models import WebhookDelivery, WebhookEndpoint

logger = logging.getLogger("config.webhooks")

_TIMEOUT = 10  # seconds
_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds – waits 2, 4, 8 …


def _sign(payload_bytes: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 hex digest for the given payload."""
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


def dispatch_event(event_type: str, payload: dict[str, Any]) -> None:
    """Send *event_type* with *payload* to every active, subscribed endpoint."""
    endpoints = WebhookEndpoint.objects.filter(is_active=True)
    for ep in endpoints:
        if event_type not in ep.events:
            continue
        _deliver(ep, event_type, payload)


def _deliver(
    endpoint: WebhookEndpoint, event_type: str, payload: dict[str, Any]
) -> None:
    """POST the payload to a single endpoint with exponential-backoff retry."""
    body = json.dumps(payload, default=str)
    body_bytes = body.encode()
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event": event_type,
        "X-Webhook-Delivery-Time": timezone.now().isoformat(),
    }
    if endpoint.secret:
        headers["X-Webhook-Signature"] = f"sha256={_sign(body_bytes, endpoint.secret)}"

    response_status = None
    response_body = ""
    success = False
    start = time.monotonic()
    attempts = 0

    for attempt in range(_MAX_RETRIES + 1):
        attempts = attempt + 1
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                resp = client.post(endpoint.url, content=body_bytes, headers=headers)
            response_status = resp.status_code
            response_body = resp.text[:2000]
            success = 200 <= resp.status_code < 300
            if success:
                break
            # Retry on server errors (5xx); stop on client errors (4xx)
            if resp.status_code < 500:
                break
        except httpx.HTTPError as exc:
            response_body = str(exc)[:2000]
            logger.warning(
                "Webhook delivery attempt %d/%d failed for %s: %s",
                attempts,
                _MAX_RETRIES + 1,
                endpoint.name,
                exc,
            )

        if attempt < _MAX_RETRIES:
            time.sleep(_BACKOFF_BASE ** (attempt + 1))

    if not success:
        logger.warning(
            "Webhook delivery to %s exhausted %d attempts", endpoint.name, attempts
        )

    duration_ms = int((time.monotonic() - start) * 1000)

    WebhookDelivery.objects.create(
        endpoint=endpoint,
        event_type=event_type,
        payload=payload,
        response_status=response_status,
        response_body=response_body,
        success=success,
        duration_ms=duration_ms,
    )
