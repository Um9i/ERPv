from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from inventory.models import Inventory, InventoryLedger, InventoryLocation

logger = logging.getLogger(__name__)


@transaction.atomic
def complete_sales_line(line) -> None:
    """Close a sales order line: deduct inventory, record ledger entries.

    Decrements stock for the ordered quantity, creates inventory and sales
    ledger entries, computes the line value, and marks the line as closed.
    This is only used for full-line completion; partial shipments are handled
    separately by the shipment view.
    """
    from sales.models import SalesLedger

    Inventory.objects.select_for_update().filter(product=line.product.product).update(
        quantity=F("quantity") - line.quantity, last_updated=timezone.now()
    )

    try:
        line.value = line.product.price * line.quantity
    except (TypeError, AttributeError):
        line.value = None

    InventoryLedger.objects.create(
        product=line.product.product,
        quantity=-abs(line.quantity),
        action=InventoryLedger.Action.SALES_ORDER,
        transaction_id=line.sales_order.pk,
    )
    SalesLedger.objects.create(
        product=line.product.product,
        quantity=line.quantity,
        customer=line.sales_order.customer,
        value=line.value or 0,
        transaction_id=line.sales_order.pk,
    )
    line.closed = True
    logger.info(
        "sales_line_completed",
        extra={
            "line_id": line.pk,
            "order_id": line.sales_order_id,
            "product_id": line.product.product_id,
            "quantity": line.quantity,
            "value": str(line.value),
        },
    )


def get_ship_context(sales_order) -> dict[str, Any]:
    """Build shipping context: annotate lines with stock info.

    Returns a dict with ``lines`` (list of order lines with stock
    annotations) and ``any_shortage`` flag.
    """
    all_lines = list(
        sales_order.sales_order_lines.select_related("product__product").all()
    )
    open_product_ids = {
        line.product.product_id for line in all_lines if not line.complete
    }
    inv_map = (
        dict(
            Inventory.objects.filter(product_id__in=open_product_ids).values_list(
                "product_id", "quantity"
            )
        )
        if open_product_ids
        else {}
    )
    any_shortage = False
    for line in all_lines:
        if line.complete:
            line.stock = None
            line.stock_ok = None
            line.max_shippable = 0
        else:
            stock = inv_map.get(line.product.product_id, 0)
            line.stock = stock
            line.stock_ok = stock >= line.remaining
            line.max_shippable = min(line.remaining, max(stock, 0))
            if not line.stock_ok:
                any_shortage = True
    return {"lines": all_lines, "any_shortage": any_shortage}


@transaction.atomic
def ship_sales_order(
    sales_order, line_quantities: dict[int, int]
) -> tuple[bool, list[str]]:
    """Ship quantities for a sales order.

    *line_quantities* maps ``SalesOrderLine.pk`` → quantity to ship.
    A key of ``None`` with value ``True`` signals "ship all remaining".

    Returns ``(touched, errors)`` where *touched* is ``True`` when any
    inventory was modified and *errors* is a list of user-facing messages.
    """
    from sales.models import SalesLedger

    ship_all = line_quantities.pop("__all__", False)
    touched = False
    errors: list[str] = []

    for line in sales_order.sales_order_lines.filter(complete=False):
        if ship_all:
            qty = line.remaining
        else:
            qty = line_quantities.get(line.id)
            if qty is None:
                continue
        if qty <= 0:
            if line.quantity_shipped >= line.quantity:
                line.complete = True
                line.closed = True
                line.save(update_fields=["complete", "closed"])
            continue

        # validate stock
        try:
            inv = Inventory.objects.select_for_update().get(
                product=line.product.product
            )
        except Inventory.DoesNotExist:
            inv = None
        if inv is None or (inv.quantity - qty) < 0:
            errors.append(
                f"Not enough inventory to ship {qty} of {line.product.product.name}."
            )
            continue

        # deduct inventory
        touched = True
        inv.quantity -= qty
        inv.save(update_fields=["quantity", "last_updated"])

        # deduct from stock locations
        remaining_to_deduct = qty
        locations_used = []
        stock_locs = list(
            InventoryLocation.objects.select_for_update()
            .filter(inventory=inv, quantity__gt=0)
            .order_by("location__name")
        )
        for sl in stock_locs:
            if remaining_to_deduct <= 0:
                break
            deduct = min(sl.quantity, remaining_to_deduct)
            sl.quantity -= deduct
            sl.save(update_fields=["quantity", "last_updated"])
            remaining_to_deduct -= deduct
            locations_used.append(sl.location)

        # ledger entries
        InventoryLedger.objects.create(
            product=line.product.product,
            quantity=-abs(qty),
            action=InventoryLedger.Action.SALES_ORDER,
            transaction_id=sales_order.pk,
            location=locations_used[0] if len(locations_used) == 1 else None,
        )
        SalesLedger.objects.create(
            product=line.product.product,
            quantity=qty,
            customer=sales_order.customer,
            value=(line.product.price or 0) * qty,
            transaction_id=sales_order.pk,
        )

        # update line
        line.quantity_shipped = line.quantity_shipped + qty
        if line.quantity_shipped >= line.quantity:
            line.complete = True
            line.closed = True
            try:
                line.value = line.product.price * line.quantity
            except Exception:
                line.value = None
        fields = ["quantity_shipped"]
        if line.complete:
            fields += ["complete", "closed", "value"]
        line.save(update_fields=fields)

    logger.info(
        "sales_order_shipped",
        extra={
            "order_id": sales_order.pk,
            "touched": touched,
            "error_count": len(errors),
        },
    )
    return touched, errors
