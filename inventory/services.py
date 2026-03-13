from __future__ import annotations

import logging
from collections.abc import Iterable

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from inventory.models import Inventory, InventoryLedger, InventoryLocation, Location

logger = logging.getLogger(__name__)


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
        logger.info(
            "required_cache_refreshed",
            extra={
                "product_ids": [u.product_id for u in updates],
                "count": len(updates),
            },
        )


@transaction.atomic
def apply_inventory_adjustment(
    adjustment,
    location: Location | None = None,
) -> None:
    """Apply an inventory adjustment and record it in the ledger.

    *adjustment* is an unsaved ``InventoryAdjust`` instance.  The function
    updates on-hand stock, creates a ledger entry, optionally routes the
    delta to *location*, and refreshes the required-stock cache.
    """

    product = adjustment.product

    # persist the adjustment row first
    adjustment.full_clean()
    adjustment.save_base()

    # update on-hand stock
    Inventory.objects.select_for_update().filter(product=product).update(
        quantity=F("quantity") + adjustment.quantity, last_updated=timezone.now()
    )

    # ledger entry
    InventoryLedger.objects.create(
        product=product,
        quantity=adjustment.quantity,
        action=InventoryLedger.Action.INVENTORY_ADJUSTMENT,
        transaction_id=product.pk,
        location=location,
    )

    # route delta to a specific bin when requested
    if location:
        inv_obj = Inventory.objects.get(product=product)
        inv_loc, _ = InventoryLocation.objects.get_or_create(
            inventory=inv_obj,
            location=location,
            defaults={"quantity": 0},
        )
        inv_loc.quantity = max(inv_loc.quantity + adjustment.quantity, 0)
        inv_loc.save()

    # refresh required-stock cache
    inv = Inventory.objects.get(product=product)
    inv.update_required_cached()

    logger.info(
        "inventory_adjusted",
        extra={
            "product_id": product.pk,
            "quantity": adjustment.quantity,
            "location": str(location) if location else None,
        },
    )
