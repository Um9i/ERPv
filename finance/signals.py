"""Signal handlers that keep the finance dashboard cache fresh."""

import logging

logger = logging.getLogger(__name__)

# Guard to prevent recursive refreshes within the same thread.
_refreshing = False


def _refresh_cache_on_ledger(sender, instance, **kwargs):
    """Refresh dashboard cache when a SalesLedger or PurchaseLedger row is created."""
    global _refreshing  # noqa: PLW0603
    if _refreshing:
        return
    _refreshing = True
    try:
        from finance.services import refresh_finance_dashboard_cache

        refresh_finance_dashboard_cache()
    except Exception:
        logger.exception("Failed to refresh finance dashboard cache (ledger signal)")
    finally:
        _refreshing = False


def _refresh_cache_on_inventory(sender, instance, **kwargs):
    """Refresh stock-value portion of the cache when inventory changes."""
    global _refreshing  # noqa: PLW0603
    if _refreshing:
        return
    _refreshing = True
    try:
        from finance.services import refresh_finance_dashboard_cache

        refresh_finance_dashboard_cache()
    except Exception:
        logger.exception("Failed to refresh finance dashboard cache (inventory signal)")
    finally:
        _refreshing = False
