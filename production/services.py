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
    Product,
    ProductionAllocated,
)
from production.models import BillOfMaterials, BOMItem, Production, ProductionLedger

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


def _collect_bom_data(root_product_id: int) -> dict:
    """Pre-fetch all BOM-related data for a product tree in bulk.

    Returns a dict with:
      - all_ids: set of all product IDs in the tree
      - edges: dict mapping parent_product_id -> [(child_product_id, qty)]
      - names: dict mapping product_id -> name
      - inv: dict mapping product_id -> on-hand quantity
    """
    from collections import defaultdict

    # Iteratively collect all product IDs in the BOM tree
    all_ids: set[int] = set()
    frontier = {root_product_id}
    while frontier:
        all_ids |= frontier
        children = set(
            BOMItem.objects.filter(bom__product_id__in=frontier).values_list(
                "product_id", flat=True
            )
        )
        frontier = children - all_ids

    # Bulk-load BOM edges: parent_product_id -> [(child_product_id, qty)]
    edges: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for parent_id, child_id, qty in BOMItem.objects.filter(
        bom__product_id__in=all_ids
    ).values_list("bom__product_id", "product_id", "quantity"):
        edges[parent_id].append((child_id, qty))

    # Bulk-load product names
    names: dict[int, str] = dict(
        Product.objects.filter(pk__in=all_ids).values_list("pk", "name")
    )

    # Bulk-load inventory quantities
    inv: dict[int, int] = dict(Inventory.objects.values_list("product_id", "quantity"))

    return {
        "all_ids": all_ids,
        "edges": edges,
        "names": names,
        "inv": inv,
    }


def compute_unit_cost(product_id: int, bom_data: dict | None = None):
    """Compute unit cost for a product using pre-fetched BOM data.

    If *bom_data* is ``None`` it will be collected from scratch, but
    callers should pass the result of ``_collect_bom_data()`` when the
    tree has already been loaded for ``build_bom_tree()``.
    """
    from django.db.models import Min

    from procurement.models import SupplierProduct

    if bom_data is None:
        bom_data = _collect_bom_data(product_id)

    all_ids = bom_data["all_ids"]
    children_map = bom_data["edges"]

    # If root has no BOM edges, it's a raw material — use cheapest supplier
    if product_id not in children_map:
        first = (
            SupplierProduct.objects.filter(product_id=product_id)
            .order_by("cost")
            .values_list("cost", flat=True)
            .first()
        )
        return first if first is not None else 0

    # Bulk-load cheapest supplier cost per product
    supplier_costs = dict(
        SupplierProduct.objects.filter(product_id__in=all_ids)
        .values("product_id")
        .annotate(min_cost=Min("cost"))
        .values_list("product_id", "min_cost")
    )

    # Bulk-load production costs per BOM
    prod_costs = dict(
        BillOfMaterials.objects.filter(product_id__in=all_ids).values_list(
            "product_id", "production_cost"
        )
    )

    # Bottom-up cost computation
    bom_pids = set(prod_costs.keys())
    costs = {
        pid: supplier_costs[pid]
        for pid in all_ids
        if pid in supplier_costs and pid not in bom_pids
    }
    changed = True
    while changed:
        changed = False
        for pid in all_ids:
            if pid in costs:
                continue
            if pid not in children_map:
                costs[pid] = 0
                changed = True
            elif all(cid in costs for cid, _ in children_map[pid]):
                component_cost = sum(qty * costs[cid] for cid, qty in children_map[pid])
                costs[pid] = component_cost + (prod_costs.get(pid) or 0)
                changed = True

    return costs.get(product_id, 0)


def build_bom_tree(product, quantity=1, bom_data=None):
    """Build a serialisable BOM tree with stock state.

    Pre-fetches all BOM edges and product names in bulk so the entire
    tree is constructed with a fixed number of queries regardless of depth.

    Pass *bom_data* (from ``_collect_bom_data``) to avoid re-querying when
    the caller has already loaded the data for ``compute_unit_cost()``.
    """
    if bom_data is None:
        bom_data = _collect_bom_data(product.pk)

    edges = bom_data["edges"]
    names = bom_data["names"]
    inv = bom_data["inv"]

    def _build(pid, qty, visited):
        if pid in visited:
            return None
        visited = visited | {pid}

        stock = inv.get(pid, 0)
        node = {
            "id": pid,
            "name": names.get(pid, ""),
            "quantity": qty,
            "stock": stock,
            "sufficient": stock >= qty,
            "children": [],
        }
        for child_id, child_qty in edges.get(pid, []):
            child = _build(child_id, child_qty * qty, visited)
            if child:
                node["children"].append(child)
        return node

    return _build(product.pk, quantity, frozenset())
