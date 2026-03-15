from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Sum
from django.db.models.functions import TruncMonth
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

    # update on-hand stock (check under lock to prevent race conditions)
    inv = Inventory.objects.select_for_update().get(product=product)
    if inv.quantity + adjustment.quantity < 0:
        raise ValidationError("Not enough resources to complete transaction.")
    inv.quantity += adjustment.quantity
    inv.last_updated = timezone.now()
    inv.save(update_fields=["quantity", "last_updated"])

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


def get_inventory_detail_context(
    inventory: Inventory, page: str | None = None
) -> dict[str, Any]:
    """Compute all context data for the inventory detail page.

    Returns a dict containing ledger pagination, running-balance chart
    history, monthly activity summaries, pending quantities, shortage
    info, and stock-location allocation.
    """
    from procurement.models import PurchaseOrderLine
    from production.models import Production
    from sales.models import SalesOrderLine

    product = inventory.product
    ctx: dict[str, Any] = {}

    # ── Ledger pagination ──
    ledger_list = product.inventory_ledger.all().order_by("-date")
    paginator = Paginator(ledger_list, 10)
    ledger_page = paginator.get_page(page)

    # ── Running balance anchored to current stock ──
    all_entries_desc = list(
        product.inventory_ledger.all().order_by("-date").values_list("pk", "quantity")
    )
    balance_map: dict[int, int] = {}
    running = inventory.quantity
    for pk, qty in all_entries_desc:
        balance_map[pk] = running
        running -= qty

    for entry in ledger_page:
        entry.balance = balance_map.get(entry.pk, None)  # type: ignore[attr-defined]
    ctx["ledger"] = ledger_page

    # ── Chart history anchored to real stock ──
    all_entries_asc = list(
        product.inventory_ledger.all().order_by("date").values_list("quantity", "date")
    )
    opening_balance = running  # leftover from desc walk
    history = []
    raw_dates = []
    total = opening_balance
    for qty, dt in all_entries_asc:
        total += qty
        raw_dates.append(dt)
        history.append(total)

    if raw_dates:
        all_same_day = len(set(d.date() for d in raw_dates)) == 1
        date_fmt = "%H:%M" if all_same_day else "%d %b"
        dates = [d.strftime(date_fmt) for d in raw_dates]
    else:
        dates = []
    ctx["history_dates"] = dates
    ctx["history_qty"] = history

    # ── Monthly activity summaries ──
    sales_months = (
        SalesOrderLine.objects.filter(product__product=product)
        .annotate(month=TruncMonth("sales_order__created_at"))
        .values("month")
        .annotate(total=Sum("quantity"))
        .order_by("month")
    )
    purchase_months = (
        PurchaseOrderLine.objects.filter(product__product=product)
        .annotate(month=TruncMonth("purchase_order__created_at"))
        .values("month")
        .annotate(total=Sum("quantity"))
        .order_by("month")
    )
    production_months = (
        Production.objects.filter(product=product)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Sum("quantity"))
        .order_by("month")
    )

    sales_map = {e["month"]: e["total"] or 0 for e in sales_months}
    purch_map = {e["month"]: e["total"] or 0 for e in purchase_months}
    prod_map = {e["month"]: e["total"] or 0 for e in production_months}
    all_months = sorted(
        set(list(sales_map.keys()) + list(purch_map.keys()) + list(prod_map.keys()))
    )

    m_dates, m_sales, m_purch, m_prod = [], [], [], []
    for m in all_months:
        m_dates.append(m.strftime("%Y-%m"))
        m_sales.append(sales_map.get(m, 0))
        m_purch.append(purch_map.get(m, 0))
        m_prod.append(prod_map.get(m, 0))
    ctx["monthly_dates"] = m_dates
    ctx["monthly_sales"] = m_sales
    ctx["monthly_purchases"] = m_purch
    ctx["monthly_production"] = m_prod

    # ── Pending quantities ──
    ctx["sales_pending"] = (
        SalesOrderLine.objects.filter(
            product__product=product, complete=False
        ).aggregate(total=Sum(F("quantity") - F("quantity_shipped")))["total"]
        or 0
    )
    ctx["purchase_pending"] = (
        PurchaseOrderLine.objects.filter(
            product__product=product, complete=False
        ).aggregate(total=Sum(F("quantity") - F("quantity_received")))["total"]
        or 0
    )
    ctx["production_pending"] = (
        Production.objects.filter(product=product, closed=False)
        .filter(quantity__gt=F("quantity_received"))
        .aggregate(total=Sum(F("quantity") - F("quantity_received")))["total"]
        or 0
    )

    # ── Shortage / required qty ──
    available = inventory.quantity + ctx["purchase_pending"] + ctx["production_pending"]
    ctx["required_qty"] = max(0, ctx["sales_pending"] - available)

    # ── Stock location allocation ──
    ctx["allocated_qty"] = (
        inventory.stock_locations.aggregate(total=Sum("quantity"))["total"] or 0
    )
    ctx["unallocated_qty"] = inventory.quantity - ctx["allocated_qty"]
    ctx["ledger_has_locations"] = product.inventory_ledger.filter(
        location__isnull=False
    ).exists()

    # ── BOM link ──
    from production.models import BillOfMaterials

    try:
        ctx["bom"] = product.billofmaterials
    except BillOfMaterials.DoesNotExist:
        ctx["bom"] = None

    # ── Purchasable (has at least one supplier) ──
    ctx["has_supplier"] = product.product_suppliers.exists()

    # ── Chart data bundle for json_script ──
    ctx["chart_data"] = {
        "sales_pending": ctx["sales_pending"],
        "purchase_pending": ctx["purchase_pending"],
        "production_pending": ctx["production_pending"],
        "required_qty": ctx["required_qty"],
        "history_dates": ctx["history_dates"],
        "history_qty": ctx["history_qty"],
        "monthly_dates": ctx["monthly_dates"],
        "monthly_sales": ctx["monthly_sales"],
        "monthly_purchases": ctx["monthly_purchases"],
        "monthly_production": ctx["monthly_production"],
    }
    return ctx
