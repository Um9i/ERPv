from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

from inventory.models import Inventory, InventoryLedger, InventoryLocation

if TYPE_CHECKING:
    from sales.models import SalesOrder, SalesOrderLine

logger = logging.getLogger(__name__)


@transaction.atomic
def complete_sales_line(line: SalesOrderLine) -> None:
    """Close a sales order line: deduct inventory, record ledger entries.

    Decrements stock for the ordered quantity, creates inventory and sales
    ledger entries, computes the line value, and marks the line as closed.
    This is only used for full-line completion; partial shipments are handled
    separately by the shipment view.
    """
    from django.core.exceptions import ValidationError
    from django.utils.translation import gettext_lazy as _

    from sales.models import SalesLedger

    inv = Inventory.objects.select_for_update().get(product=line.product.product)
    if inv.quantity < line.quantity:
        raise ValidationError(_("Not enough resources to complete transaction."))
    inv.quantity -= line.quantity
    inv.last_updated = timezone.now()
    inv.save(update_fields=["quantity", "last_updated"])

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


def get_ship_context(sales_order: SalesOrder) -> dict[str, Any]:
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
            line.stock = None  # type: ignore[attr-defined]
            line.stock_ok = None  # type: ignore[attr-defined]
            line.max_shippable = 0  # type: ignore[attr-defined]
        else:
            stock = inv_map.get(line.product.product_id, 0)
            line.stock = stock  # type: ignore[attr-defined]
            line.stock_ok = stock >= line.remaining  # type: ignore[attr-defined]
            line.max_shippable = min(line.remaining, max(stock, 0))  # type: ignore[attr-defined]
            if not line.stock_ok:  # type: ignore[attr-defined]
                any_shortage = True
    return {"lines": all_lines, "any_shortage": any_shortage}


@transaction.atomic
def ship_sales_order(
    sales_order,
    line_quantities: dict[int, int],
    *,
    ship_all: bool = False,
) -> tuple[bool, list[str]]:
    """Ship quantities for a sales order.

    *line_quantities* maps ``SalesOrderLine.pk`` → quantity to ship.
    When *ship_all* is ``True``, all remaining quantities are shipped.

    Returns ``(touched, errors)`` where *touched* is ``True`` when any
    inventory was modified and *errors* is a list of user-facing messages.
    """
    from sales.models import SalesLedger

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


def populate_pick_list_lines(pick_list) -> None:
    """Create pick lines based on current stock levels.

    Bulk-loads all required Inventory and InventoryLocation rows up front to
    avoid per-line queries inside the loop.
    """
    from django.db.models import Sum

    from sales.models import PickListLine

    open_lines = list(
        pick_list.sales_order.sales_order_lines.filter(complete=False).select_related(
            "product__product"
        )
    )
    product_ids = [line.product.product_id for line in open_lines]

    inv_map = {
        inv.product_id: inv
        for inv in Inventory.objects.filter(product_id__in=product_ids)
    }
    stock_locs_map: dict[int, list] = {pid: [] for pid in product_ids}
    for sl in (
        InventoryLocation.objects.filter(
            inventory__product_id__in=product_ids, quantity__gt=0
        )
        .select_related("location")
        .order_by("location__name")
    ):
        stock_locs_map[sl.inventory.product_id].append(sl)

    loc_totals_map: dict[int, int] = {
        row["inventory__product_id"]: row["total"]
        for row in InventoryLocation.objects.filter(
            inventory__product_id__in=product_ids
        )
        .values("inventory__product_id")
        .annotate(total=Sum("quantity"))
    }

    lines_to_create = []
    for line in open_lines:
        remaining = line.remaining
        if remaining <= 0:
            continue
        product_id = line.product.product_id
        inv = inv_map.get(product_id)
        if inv is None:
            lines_to_create.append(
                PickListLine(
                    pick_list=pick_list,
                    sales_order_line=line,
                    location=None,
                    quantity=remaining,
                )
            )
            continue

        stock_locs = stock_locs_map.get(product_id, [])
        allocated = 0
        for sl in stock_locs:
            if allocated >= remaining:
                break
            pick_qty = min(sl.quantity, remaining - allocated)
            lines_to_create.append(
                PickListLine(
                    pick_list=pick_list,
                    sales_order_line=line,
                    location=sl.location,
                    quantity=pick_qty,
                )
            )
            allocated += pick_qty

        if allocated < remaining:
            loc_total = loc_totals_map.get(product_id, 0)
            unallocated_qty = max(inv.quantity - loc_total, 0)
            if unallocated_qty > 0:
                pick_qty = min(unallocated_qty, remaining - allocated)
                lines_to_create.append(
                    PickListLine(
                        pick_list=pick_list,
                        sales_order_line=line,
                        location=None,
                        quantity=pick_qty,
                    )
                )
                allocated += pick_qty

        if allocated < remaining:
            lines_to_create.append(
                PickListLine(
                    pick_list=pick_list,
                    sales_order_line=line,
                    location=None,
                    quantity=remaining - allocated,
                    is_shortage=True,
                )
            )

    PickListLine.objects.bulk_create(lines_to_create)


def refresh_unconfirmed_pick_lines(pick_list) -> None:
    """Re-check stock for unconfirmed lines, preserving confirmed ones.

    Bulk-loads Inventory and InventoryLocation up front to avoid per-line queries.
    """
    from django.db.models import Sum

    from sales.models import PickListLine

    pick_list.lines.filter(confirmed=False).delete()

    confirmed_by_sol = (
        pick_list.lines.filter(confirmed=True)
        .values("sales_order_line_id")
        .annotate(confirmed_qty=Sum("quantity"))
    )
    confirmed_map = {
        row["sales_order_line_id"]: row["confirmed_qty"] for row in confirmed_by_sol
    }

    open_lines = list(
        pick_list.sales_order.sales_order_lines.filter(complete=False).select_related(
            "product__product"
        )
    )
    product_ids = [line.product.product_id for line in open_lines]

    inv_map = {
        inv.product_id: inv
        for inv in Inventory.objects.filter(product_id__in=product_ids)
    }
    stock_locs_map: dict[int, list] = {pid: [] for pid in product_ids}
    for sl in (
        InventoryLocation.objects.filter(
            inventory__product_id__in=product_ids, quantity__gt=0
        )
        .select_related("location")
        .order_by("location__name")
    ):
        stock_locs_map[sl.inventory.product_id].append(sl)

    loc_totals_map: dict[int, int] = {
        row["inventory__product_id"]: row["total"]
        for row in InventoryLocation.objects.filter(
            inventory__product_id__in=product_ids
        )
        .values("inventory__product_id")
        .annotate(total=Sum("quantity"))
    }

    # per-line confirmed-location maps (still per-line but data already in memory)
    confirmed_locs_map: dict[int, dict[int, int]] = {}
    for row in (
        pick_list.lines.filter(confirmed=True, location__isnull=False)
        .values("sales_order_line_id", "location_id")
        .annotate(used=Sum("quantity"))
    ):
        confirmed_locs_map.setdefault(row["sales_order_line_id"], {})[
            row["location_id"]
        ] = row["used"]

    confirmed_unallocated_map: dict[int, int] = {
        row["sales_order_line_id"]: row["used"]
        for row in pick_list.lines.filter(confirmed=True, location__isnull=True)
        .values("sales_order_line_id")
        .annotate(used=Sum("quantity"))
    }

    lines_to_create = []
    for line in open_lines:
        already_confirmed = confirmed_map.get(line.pk, 0)
        remaining = line.remaining - already_confirmed
        if remaining <= 0:
            continue
        product_id = line.product.product_id
        inv = inv_map.get(product_id)
        if inv is None:
            lines_to_create.append(
                PickListLine(
                    pick_list=pick_list,
                    sales_order_line=line,
                    location=None,
                    quantity=remaining,
                    is_shortage=True,
                )
            )
            continue

        confirmed_loc_map = confirmed_locs_map.get(line.pk, {})
        stock_locs = stock_locs_map.get(product_id, [])
        allocated = 0
        for sl in stock_locs:
            if allocated >= remaining:
                break
            available = sl.quantity - confirmed_loc_map.get(sl.location_id, 0)
            if available <= 0:
                continue
            pick_qty = min(available, remaining - allocated)
            lines_to_create.append(
                PickListLine(
                    pick_list=pick_list,
                    sales_order_line=line,
                    location=sl.location,
                    quantity=pick_qty,
                )
            )
            allocated += pick_qty

        if allocated < remaining:
            loc_total = loc_totals_map.get(product_id, 0)
            unallocated_qty = max(inv.quantity - loc_total, 0)
            confirmed_unallocated = confirmed_unallocated_map.get(line.pk, 0)
            unallocated_qty = max(unallocated_qty - confirmed_unallocated, 0)
            if unallocated_qty > 0:
                pick_qty = min(unallocated_qty, remaining - allocated)
                lines_to_create.append(
                    PickListLine(
                        pick_list=pick_list,
                        sales_order_line=line,
                        location=None,
                        quantity=pick_qty,
                    )
                )
                allocated += pick_qty

        if allocated < remaining:
            lines_to_create.append(
                PickListLine(
                    pick_list=pick_list,
                    sales_order_line=line,
                    location=None,
                    quantity=remaining - allocated,
                    is_shortage=True,
                )
            )

    PickListLine.objects.bulk_create(lines_to_create)
