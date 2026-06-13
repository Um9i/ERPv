from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from django.shortcuts import redirect as _redirect
from django.utils.http import url_has_allowed_host_and_scheme


def safe_redirect(url: str, fallback: str = "/"):
    """Redirect to *url* only when it is a safe, same-origin path.

    Prevents open-redirect vulnerabilities (CWE-601) when the redirect
    target originates from user-controlled request data such as
    ``request.path`` or ``request.get_full_path()``.
    """
    if url_has_allowed_host_and_scheme(url, allowed_hosts=None):
        return _redirect(url)
    return _redirect(fallback)


def make_order_total_cache_receiver(
    order_attr: str,
    order_id_attr: str,
    logger: logging.Logger,
) -> Callable[..., None]:
    """Return a Django signal receiver that refreshes an order's cached total.

    Generates a ``post_save`` / ``post_delete`` handler for order-line models
    that calls ``order.update_cached_total()`` and logs any failure.

    Args:
        order_attr: Attribute name on the line instance pointing to the parent order (e.g. ``"sales_order"``).
        order_id_attr: Attribute holding the FK id for log context (e.g. ``"sales_order_id"``).
        logger: Module-level logger to use for exception reporting.
    """

    def _handler(sender: Any, instance: Any, **kwargs: Any) -> None:
        try:
            getattr(instance, order_attr).update_cached_total()
        except Exception:
            logger.exception(
                "Failed to update cached total for %s", getattr(instance, order_id_attr)
            )

    return _handler
