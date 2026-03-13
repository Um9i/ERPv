"""Signal handlers that keep the finance dashboard cache fresh."""

import logging
import threading

logger = logging.getLogger(__name__)

# Thread-local guard to prevent recursive refreshes.
_state = threading.local()


def _refresh_finance_cache(sender, instance, **kwargs):
    """Refresh dashboard cache when a ledger or inventory row changes."""
    if getattr(_state, "refreshing", False):
        return
    _state.refreshing = True
    try:
        from finance.services import refresh_finance_dashboard_cache

        refresh_finance_dashboard_cache()
    except Exception:
        logger.exception(
            "Failed to refresh finance dashboard cache (%s signal)",
            sender.__name__,
        )
    finally:
        _state.refreshing = False
