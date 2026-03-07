from __future__ import annotations

from collections.abc import Iterable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum, F

from inventory.models import Inventory, InventoryLedger, InventoryLocation, Location
from production.models import BillOfMaterials, Production


@transaction.atomic
def receive_production_into_location(production_id, quantity_to_receive, location_id):
    """Receive finished goods from a production job into a specific inventory location.

    This wraps Production.save() with the delta, then adjusts InventoryLocation.
    The total Inventory.quantity is already updated by Production.save() —
    we just need to route that quantity to the right bin.
    """
    job = Production.objects.select_for_update().get(pk=production_id)
    location = Location.objects.get(pk=location_id)

    if quantity_to_receive <= 0:
        raise ValidationError("Quantity must be positive.")
    if quantity_to_receive > job.remaining:
        raise ValidationError(
            f"Cannot receive {quantity_to_receive} — only {job.remaining} remaining."
        )

    # let Production.save() handle all the BOM deductions, ledger entries,
    # allocation updates, and closing logic
    prev_received = job.quantity_received
    job.quantity_received = prev_received + quantity_to_receive
    job.save()  # all existing logic fires here

    # now route the finished goods to the specified location
    inv = Inventory.objects.get(product=job.product)
    inv_loc, _ = InventoryLocation.objects.get_or_create(
        inventory=inv,
        location=location,
        defaults={"quantity": 0},
    )
    inv_loc.quantity += quantity_to_receive
    inv_loc.save()

    # tag the ledger entry that Production.save() just created
    # with the destination location
    entry = (
        InventoryLedger.objects.filter(
            product=job.product,
            action="Production",
            transaction_id=job.pk,
            location__isnull=True,
        )
        .order_by("-date")
        .first()
    )
    if entry:
        entry.location = location
        entry.save(update_fields=["location"])


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
