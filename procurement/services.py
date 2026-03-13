from __future__ import annotations

import logging
from collections.abc import Iterable
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from procurement.models import PurchaseLedger, PurchaseOrderLine, SupplierProduct

logger = logging.getLogger(__name__)


def supplier_cost_totals() -> dict[int, Decimal]:
    totals = (
        SupplierProduct.objects.values("supplier")
        .annotate(total=Sum("cost"))
        .order_by("supplier")
    )
    return {entry["supplier"]: Decimal(entry["total"] or 0) for entry in totals}


def best_supplier_products(product_ids: Iterable[int]) -> dict[int, SupplierProduct]:
    """Pick the cheapest supplier product per product id.

    Ties on cost are broken by comparing the supplier's aggregate cost across
    all products (lower total wins) to spread purchasing across more economical
    suppliers.
    """
    supplier_totals = supplier_cost_totals()
    sp_qs = SupplierProduct.objects.filter(product_id__in=product_ids).order_by(
        "product_id", "cost"
    )
    best: dict[int, SupplierProduct] = {}
    for sp in sp_qs:
        current = best.get(sp.product_id)
        if current is None:
            best[sp.product_id] = sp
            continue
        if sp.cost < current.cost:
            best[sp.product_id] = sp
            continue
        if sp.cost == current.cost:
            curr_total = supplier_totals.get(current.supplier_id, 0)
            cand_total = supplier_totals.get(sp.supplier_id, 0)
            if cand_total < curr_total:
                best[sp.product_id] = sp
    return best


def pending_po_by_product(product_ids: Iterable[int]) -> dict[int, int]:
    po_vals = (
        PurchaseOrderLine.objects.filter(
            product__product_id__in=product_ids, complete=False
        )
        .annotate(rem=F("quantity") - F("quantity_received"))
        .values("product__product_id")
        .annotate(total=Sum("rem"))
    )
    return {row["product__product_id"]: int(row["total"] or 0) for row in po_vals}


@transaction.atomic
def receive_purchase_order_line(line: PurchaseOrderLine, qty: int) -> int | None:
    """Receive *qty* units against a purchase order line.

    Updates inventory, creates ledger entries, routes stock to a single
    bin location when applicable, and marks the line complete once fully
    received.  Returns the product id of the affected inventory item (so
    callers can batch ``refresh_required_cache_for_products``), or ``None``
    if *qty* is not positive.
    """
    if qty <= 0:
        return None

    from inventory.models import Inventory, InventoryLedger, InventoryLocation

    product = line.product.product  # the catalogue Product

    # increase on-hand stock
    Inventory.objects.select_for_update().filter(product=product).update(
        quantity=F("quantity") + qty, last_updated=timezone.now()
    )

    # route to single-bin location when applicable
    inv_obj = Inventory.objects.get(product=product)
    stock_locs = list(inv_obj.stock_locations.all())
    recv_location = None
    if len(stock_locs) == 1:
        sl = InventoryLocation.objects.select_for_update().get(pk=stock_locs[0].pk)
        sl.quantity += qty
        sl.save(update_fields=["quantity", "last_updated"])
        recv_location = sl.location

    # ledger entries
    InventoryLedger.objects.create(
        product=product,
        quantity=qty,
        action=InventoryLedger.Action.PURCHASE_ORDER,
        transaction_id=line.purchase_order_id,
        location=recv_location,
    )
    PurchaseLedger.objects.create(
        product=product,
        quantity=qty,
        supplier=line.purchase_order.supplier,
        value=(line.product.cost or 0) * qty,
        transaction_id=line.purchase_order_id,
    )

    # update the line's received tally
    line.quantity_received = line.quantity_received + qty
    fields = ["quantity_received"]
    if line.quantity_received >= line.quantity:
        line.complete = True
        line.closed = True
        try:
            line.value = line.product.cost * line.quantity
        except Exception:
            line.value = None
        fields += ["complete", "closed", "value"]
    line.save(update_fields=fields)

    logger.info(
        "purchase_order_line_received",
        extra={
            "line_id": line.pk,
            "po_id": line.purchase_order_id,
            "product_id": product.pk,
            "qty_received": qty,
            "fully_received": line.complete,
        },
    )

    return product.pk
