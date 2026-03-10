from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from django.db.models import F, Sum

from procurement.models import PurchaseOrderLine, SupplierProduct


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
