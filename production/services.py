from __future__ import annotations

from collections.abc import Iterable

from django.db.models import Sum, F

from inventory.models import Inventory
from production.models import BillOfMaterials, Production


def bom_product_ids(product_ids: Iterable[int]) -> set[int]:
    return set(
        BillOfMaterials.objects.filter(product_id__in=product_ids).values_list(
            "product_id", flat=True
        )
    )


def pending_jobs_by_product(product_ids: Iterable[int]) -> dict[int, int]:
    job_vals = (
        Production.objects.filter(product_id__in=product_ids, closed=False)
        .annotate(rem=F("quantity") - F("quantity_received"))
        .values("product_id")
        .annotate(total=Sum("rem"))
    )
    return {row["product_id"]: int(row["total"] or 0) for row in job_vals}


def build_bom_tree(product, quantity=1, visited=None):
    """Recursively build a serialisable BOM tree with stock state."""
    if visited is None:
        visited = set()
    if product.pk in visited:
        return None  # circular reference guard
    visited = visited | {product.pk}

    try:
        inv = Inventory.objects.get(product=product)
        stock = inv.quantity
    except Inventory.DoesNotExist:
        stock = 0

    node = {
        "id": product.pk,
        "name": product.name,
        "quantity": quantity,
        "stock": stock,
        "sufficient": stock >= quantity,
        "children": [],
    }

    try:
        bom = product.billofmaterials
        for item in bom.bom_items.select_related("product").all():
            child = build_bom_tree(
                item.product,
                quantity=item.quantity * quantity,
                visited=visited,
            )
            if child:
                node["children"].append(child)
    except product.__class__.billofmaterials.RelatedObjectDoesNotExist:
        pass

    return node
