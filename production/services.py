from __future__ import annotations

import logging
from collections.abc import Iterable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum

from inventory.models import (
    Inventory,
    InventoryLedger,
    InventoryLocation,
    Location,
    ProductionAllocated,
)
from production.models import BillOfMaterials, Production, ProductionLedger

logger = logging.getLogger(__name__)


@transaction.atomic
def allocate_production(job: Production) -> None:
    """Allocate BOM components for a production job.

    Increments the ``ProductionAllocated`` quantities for each component and
    marks the job as allocated.  Raises ``ValidationError`` if the product has
    no bill of materials.
    """
    bom_items = job.bom()
    if bom_items is None:
        raise ValidationError("Product has no Bill of Materials.")

    for item in bom_items:
        alloc = ProductionAllocated.objects.select_for_update().get(
            product=item.product
        )
        alloc.quantity = (alloc.quantity or 0) + item.quantity * job.quantity
        alloc.save()

    job.bom_allocated = True
    job.bom_allocated_amount = job.quantity
    logger.info(
        "production_allocated",
        extra={
            "job_id": job.pk,
            "product_id": job.product_id,
            "quantity": job.quantity,
        },
    )


@transaction.atomic
def receive_production(job: Production, delta: int) -> set[int]:
    """Receive ``delta`` units of a production job.

    Validates component stock, increases finished product inventory,
    decreases component inventories and allocations, and creates ledger
    entries.  Returns the set of affected product IDs so callers can
    refresh caches.
    """
    if delta <= 0:
        return set()

    bom_items = job.bom()
    affected_product_ids: set[int] = set()

    # ensure all components have enough stock
    if bom_items is not None:
        for item in bom_items:
            inv = Inventory.objects.select_for_update().get(product=item.product)
            if inv.quantity - item.quantity * delta < 0:
                raise ValidationError("Not enough Inventory to complete production.")

    # increase finished product
    prod_obj = Inventory.objects.select_for_update().get(product=job.product)
    prod_obj.quantity = prod_obj.quantity + delta
    prod_obj.save()
    affected_product_ids.add(job.product_id)

    # deduct components and create ledger entries
    if bom_items is not None:
        for item in bom_items:
            qty_change = item.quantity * delta
            Inventory.objects.select_for_update().filter(product=item.product).update(
                quantity=F("quantity") - qty_change
            )
            ProductionAllocated.objects.select_for_update().filter(
                product=item.product
            ).update(quantity=F("quantity") - qty_change)
            InventoryLedger.objects.create(
                product=item.product,
                quantity=-abs(qty_change),
                action=InventoryLedger.Action.PRODUCTION,
                transaction_id=job.pk,
            )
            affected_product_ids.add(item.product_id)
        InventoryLedger.objects.create(
            product=job.product,
            quantity=delta,
            action=InventoryLedger.Action.PRODUCTION,
            transaction_id=job.pk,
        )

    # create production ledger entry for the finished goods received
    unit_cost = job.product.unit_cost or 0
    ProductionLedger.objects.create(
        product=job.product,
        quantity=delta,
        value=unit_cost * delta,
        transaction_id=job.pk,
    )

    # mark complete if fully received
    if job.quantity_received >= job.quantity:
        job.closed = True
        job.complete = True
        logger.info(
            "production_completed",
            extra={"job_id": job.pk, "product_id": job.product_id},
        )

    logger.info(
        "production_received",
        extra={
            "job_id": job.pk,
            "product_id": job.product_id,
            "delta": delta,
            "affected_products": list(affected_product_ids),
        },
    )
    return affected_product_ids


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

    logger.info(
        "production_received_into_location",
        extra={
            "job_id": production_id,
            "location_id": location_id,
            "quantity": quantity_to_receive,
        },
    )


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


def build_bom_tree(product, quantity=1, visited=None, _inv_cache=None):
    """Recursively build a serialisable BOM tree with stock state."""
    if visited is None:
        visited = set()
    if product.pk in visited:
        return None  # circular reference guard
    visited = visited | {product.pk}

    # on first call, pre-fetch all inventory into a cache
    if _inv_cache is None:
        _inv_cache = dict(Inventory.objects.values_list("product_id", "quantity"))

    stock = _inv_cache.get(product.pk, 0)

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
                _inv_cache=_inv_cache,
            )
            if child:
                node["children"].append(child)
    except product.__class__.billofmaterials.RelatedObjectDoesNotExist:
        pass

    return node
