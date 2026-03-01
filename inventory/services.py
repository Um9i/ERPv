from __future__ import annotations

from collections.abc import Iterable

from inventory.models import Inventory


def refresh_required_cache_for_products(product_ids: Iterable[int]) -> None:
    """Recompute and persist ``required_cached`` for the given products.

    The set of product ids is deduplicated to avoid redundant queries.
    Updates are only issued when the cached value differs from the live
    ``required`` computation so callers can invoke this freely after any
    inventory-impacting operation.
    """
    ids = {pid for pid in product_ids if pid is not None}
    if not ids:
        return

    updates: list[Inventory] = []
    for inv in Inventory.objects.select_related("product").filter(product_id__in=ids):
        required_val = inv.required
        if inv.required_cached != required_val:
            inv.required_cached = required_val
            updates.append(inv)

    if updates:
        Inventory.objects.bulk_update(updates, ["required_cached"])
