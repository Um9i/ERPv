"""Signal handlers that keep the finance dashboard cache fresh."""

import logging
import threading

logger = logging.getLogger(__name__)

# Thread-local guard to prevent recursive refreshes.
_state = threading.local()


def _refresh_cache_on_ledger(sender, instance, **kwargs):
    """Refresh dashboard cache when a SalesLedger or PurchaseLedger row is created."""
    if getattr(_state, "refreshing", False):
        return
    _state.refreshing = True
    try:
        from finance.services import refresh_finance_dashboard_cache

        refresh_finance_dashboard_cache()
    except Exception:
        logger.exception("Failed to refresh finance dashboard cache (ledger signal)")
    finally:
        _state.refreshing = False


def _refresh_cache_on_inventory(sender, instance, **kwargs):
    """Refresh stock-value portion of the cache when inventory changes."""
    if getattr(_state, "refreshing", False):
        return
    _state.refreshing = True
    try:
        from finance.services import refresh_finance_dashboard_cache

        refresh_finance_dashboard_cache()
    except Exception:
        logger.exception("Failed to refresh finance dashboard cache (inventory signal)")
    finally:
        _state.refreshing = False
