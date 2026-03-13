from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from inventory.models import Inventory, InventoryLedger

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
