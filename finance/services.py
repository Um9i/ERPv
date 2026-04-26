"""Service functions for refreshing the finance dashboard cache."""

import logging
from datetime import date, datetime
from decimal import Decimal

from django.db.models import DecimalField, Min, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from finance.models import FinanceDashboardSnapshot
from inventory.models import Inventory
from procurement.models import PurchaseLedger, SupplierProduct
from production.models import BOMItem
from sales.models import SalesLedger

logger = logging.getLogger(__name__)


def refresh_finance_dashboard_cache() -> FinanceDashboardSnapshot:
    """Recompute all dashboard aggregates and persist to the snapshot row."""

    snapshot = FinanceDashboardSnapshot.load()

    # ── All-time totals ──
    snapshot.sales_total = SalesLedger.objects.aggregate(
        total=Coalesce(Sum("value"), Decimal("0"))
    )["total"]

    snapshot.purchase_total = PurchaseLedger.objects.aggregate(
        total=Coalesce(Sum("value"), Decimal("0"))
    )["total"]

    # ── Current-month totals ──
    now = timezone.now()
    month_filter = {"date__year": now.year, "date__month": now.month}
    snapshot.month_sales_total = SalesLedger.objects.filter(**month_filter).aggregate(
        total=Coalesce(Sum("value"), Decimal("0"))
    )["total"]
    snapshot.month_purchase_total = PurchaseLedger.objects.filter(
        **month_filter
    ).aggregate(total=Coalesce(Sum("value"), Decimal("0")))["total"]
    snapshot.month_year = now.year
    snapshot.month_month = now.month

    # ── 12-month chart data ──
    today = now.date()
    first_of_month = today.replace(day=1)
    chart_months: list[date] = []
    for i in range(11, -1, -1):
        m = first_of_month.month - i
        y = first_of_month.year
        while m <= 0:
            m += 12
            y -= 1
        chart_months.append(date(y, m, 1))

    from_dt = timezone.make_aware(
        datetime(chart_months[0].year, chart_months[0].month, 1)
    )
    sales_monthly = (
        SalesLedger.objects.filter(date__gte=from_dt)
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total=Sum("value"))
        .order_by("month")
    )
    purchases_monthly = (
        PurchaseLedger.objects.filter(date__gte=from_dt)
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total=Sum("value"))
        .order_by("month")
    )
    sales_lu = {
        entry["month"].strftime("%Y-%m"): float(entry["total"])
        for entry in sales_monthly
    }
    purchases_lu = {
        entry["month"].strftime("%Y-%m"): float(entry["total"])
        for entry in purchases_monthly
    }
    month_labels = [m.strftime("%Y-%m") for m in chart_months]
    snapshot.chart_data = {
        "months": month_labels,
        "sales": [sales_lu.get(m, 0) for m in month_labels],
        "purchases": [purchases_lu.get(m, 0) for m in month_labels],
    }

    # ── Stock value ──
    snapshot.stock_value = _compute_stock_value()

    snapshot.save()
    logger.info("Finance dashboard cache refreshed at %s", snapshot.updated_at)
    return snapshot


def _compute_stock_value() -> Decimal:
    """Supplier-cost stock value with BOM fallback for un-priced products."""
    min_cost_sq = (
        SupplierProduct.objects.filter(product=OuterRef("product"))
        .values("product")
        .annotate(mc=Min("cost"))
        .values("mc")[:1]
    )
    inventories = list(
        Inventory.objects.annotate(
            unit_cost=Subquery(min_cost_sq, output_field=DecimalField()),
        ).values_list("product_id", "quantity", "unit_cost")
    )
    no_cost_ids = [pid for pid, qty, cost in inventories if cost is None and qty]
    bom_costs: dict[int, Decimal] = {}
    if no_cost_ids:
        bom_items = (
            BOMItem.objects.filter(bom__product_id__in=no_cost_ids)
            .annotate(
                comp_cost=Subquery(
                    SupplierProduct.objects.filter(product=OuterRef("product"))
                    .values("product")
                    .annotate(mc=Min("cost"))
                    .values("mc")[:1],
                    output_field=DecimalField(),
                )
            )
            .values_list("bom__product_id", "quantity", "comp_cost")
        )
        for parent_id, bom_qty, comp_cost in bom_items:
            if comp_cost is not None:
                bom_costs[parent_id] = (
                    bom_costs.get(parent_id, Decimal(0)) + bom_qty * comp_cost
                )

    total: Decimal = Decimal(0)
    for pid, qty, cost in inventories:
        effective = cost if cost is not None else bom_costs.get(pid, Decimal(0))
        total += qty * effective
    return total
