import random
import time
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F, OuterRef, Subquery, Sum
from django.utils import timezone
from faker import Faker

from finance.services import refresh_finance_dashboard_cache
from inventory.models import (
    Inventory,
    InventoryLedger,
    InventoryLocation,
    Location,
    ProductionAllocated,
)
from main.factories import CustomerFactory, ProductFactory, SupplierFactory
from procurement.models import (
    PurchaseLedger,
    PurchaseOrder,
    PurchaseOrderLine,
    SupplierContact,
    SupplierProduct,
)
from production.models import BillOfMaterials, BOMItem, Production, ProductionLedger
from sales.models import (
    CustomerContact,
    CustomerProduct,
    SalesLedger,
    SalesOrder,
    SalesOrderLine,
)

fake = Faker()

BATCH_SIZE = 500

# Warehouse location hierarchy
WAREHOUSE_STRUCTURE: dict[str, dict[str, list[str]]] = {
    "Warehouse A": {
        "Receiving": ["Bay R1", "Bay R2"],
        "Zone 1": ["Aisle 1-A", "Aisle 1-B", "Aisle 1-C"],
        "Zone 2": ["Aisle 2-A", "Aisle 2-B", "Aisle 2-C"],
        "Shipping": ["Bay S1", "Bay S2"],
    },
    "Warehouse B": {
        "Zone 1": ["Bin B1-1", "Bin B1-2", "Bin B1-3"],
        "Zone 2": ["Bin B2-1", "Bin B2-2"],
    },
}


class Command(BaseCommand):
    help = "Seed the database with generated data (optimized for speed)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--years",
            type=int,
            default=1,
            help="Number of years of history to generate (max 1, default 1)",
        )
        parser.add_argument(
            "--customers",
            type=int,
            default=20,
            help="How many customers to create",
        )
        parser.add_argument(
            "--suppliers",
            type=int,
            default=10,
            help="How many suppliers to create",
        )
        parser.add_argument(
            "--products",
            type=int,
            default=50,
            help="How many product records to create",
        )

    def handle(self, *args, **options):
        years = min(options["years"], 1)
        num_customers = options["customers"]
        num_suppliers = options["suppliers"]
        num_products = options["products"]

        start_date = timezone.now() - timedelta(days=365 * years)
        now = timezone.now()
        total_days = (now - start_date).days

        self.stdout.write(
            f"Seeding {years} year ({total_days} days) from {start_date.date()}..."
        )
        t0 = time.monotonic()

        with transaction.atomic():
            self._seed(
                start_date, now, total_days, num_customers, num_suppliers, num_products
            )

        elapsed = time.monotonic() - t0
        self.stdout.write(self.style.SUCCESS(f"Seeding complete in {elapsed:.1f}s"))

    # ------------------------------------------------------------------
    def _log(self, msg):
        self.stdout.write(f"  {msg}")

    # ------------------------------------------------------------------
    def _create_locations(self) -> list[Location]:
        """Create a realistic warehouse location hierarchy."""
        self._log("Creating warehouse locations...")
        leaf_locations: list[Location] = []
        for wh_name, zones in WAREHOUSE_STRUCTURE.items():
            wh = Location.objects.create(name=wh_name)
            for zone_name, bins in zones.items():
                zone = Location.objects.create(name=zone_name, parent=wh)
                for bin_name in bins:
                    loc = Location.objects.create(name=bin_name, parent=zone)
                    leaf_locations.append(loc)
        return leaf_locations

    # ------------------------------------------------------------------
    def _seed(
        self, start_date, now, total_days, num_customers, num_suppliers, num_products
    ):
        # ── 1. Warehouse locations ───────────────────────────────
        leaf_locations = self._create_locations()

        # ── 2. Base entities ─────────────────────────────────────
        self._log("Creating products...")
        products = ProductFactory.create_batch(num_products)

        # Set sale_price and catalogue_item on ~60% of products
        catalogue_products = random.sample(products, int(len(products) * 0.6))
        for prod in catalogue_products:
            prod.sale_price = Decimal(str(round(random.uniform(10, 600), 2)))
            prod.catalogue_item = True
        from inventory.models import Product

        Product.objects.bulk_update(
            catalogue_products, ["sale_price", "catalogue_item"], batch_size=BATCH_SIZE
        )

        self._log("Creating customers...")
        customers = CustomerFactory.create_batch(num_customers)

        self._log("Creating suppliers...")
        suppliers = SupplierFactory.create_batch(num_suppliers)

        # ── 2b. Create contacts for customers and suppliers ──────
        self._log("Creating customer contacts...")
        cc_objs = []
        for cust in customers:
            for _ in range(random.randint(1, 3)):
                cc_objs.append(
                    CustomerContact(
                        customer=cust,
                        name=fake.name(),
                        phone=fake.phone_number(),
                        email=fake.company_email(),
                        address_line_1=fake.street_address(),
                        city=fake.city(),
                        state=fake.state_abbr(),
                        postal_code=fake.postcode(),
                        country=fake.country(),
                    )
                )
        CustomerContact.objects.bulk_create(cc_objs, batch_size=BATCH_SIZE)

        self._log("Creating supplier contacts...")
        sc_objs = []
        for supp in suppliers:
            for _ in range(random.randint(1, 3)):
                sc_objs.append(
                    SupplierContact(
                        supplier=supp,
                        name=fake.name(),
                        phone=fake.phone_number(),
                        email=fake.company_email(),
                        address_line_1=fake.street_address(),
                        city=fake.city(),
                        state=fake.state_abbr(),
                        postal_code=fake.postcode(),
                        country=fake.country(),
                    )
                )
        SupplierContact.objects.bulk_create(sc_objs, batch_size=BATCH_SIZE)

        # ── 3. Link products ↔ customers / suppliers ─────────────
        self._log("Linking customer ↔ product relationships...")
        cp_objs = []
        for cust in customers:
            n = random.randint(3, min(10, len(products)))
            for prod in random.sample(products, n):
                base = (
                    float(prod.sale_price)
                    if prod.sale_price
                    else random.uniform(10, 500)
                )
                # Customer price varies ±15% from base
                price = round(base * random.uniform(0.85, 1.15), 2)
                cp_objs.append(
                    CustomerProduct(
                        customer=cust,
                        product=prod,
                        price=Decimal(str(price)),
                    )
                )
        CustomerProduct.objects.bulk_create(cp_objs, batch_size=BATCH_SIZE)

        cust_prod_map: dict[int, list[CustomerProduct]] = defaultdict(list)
        for cp in CustomerProduct.objects.select_related("customer", "product"):
            cust_prod_map[cp.customer_id].append(cp)

        self._log("Linking supplier ↔ product relationships...")
        sp_objs = []
        seen_sp: set[tuple[int, int]] = set()
        for supp in suppliers:
            n = random.randint(3, min(10, len(products)))
            for prod in random.sample(products, n):
                key = (supp.pk, prod.pk)
                if key in seen_sp:
                    continue
                seen_sp.add(key)
                base = (
                    float(prod.sale_price) * 0.5
                    if prod.sale_price
                    else random.uniform(2, 200)
                )
                cost = round(base * random.uniform(0.8, 1.2), 2)
                sp_objs.append(
                    SupplierProduct(
                        supplier=supp,
                        product=prod,
                        cost=Decimal(str(cost)),
                    )
                )
        SupplierProduct.objects.bulk_create(sp_objs, batch_size=BATCH_SIZE)

        supp_prod_map: dict[int, list[SupplierProduct]] = defaultdict(list)
        for sp in SupplierProduct.objects.select_related("supplier", "product"):
            supp_prod_map[sp.supplier_id].append(sp)

        # ── 4. Set starting inventory and distribute to locations ─
        self._log("Setting initial inventory quantities...")
        inventories = list(Inventory.objects.all())
        for inv in inventories:
            inv.quantity = random.randint(5, 80)
        Inventory.objects.bulk_update(inventories, ["quantity"], batch_size=BATCH_SIZE)

        self._log("Distributing inventory to warehouse locations...")
        inv_loc_objs = []
        for inv in inventories:
            remaining = inv.quantity
            if remaining == 0:
                continue
            # Spread across 1-4 random locations
            locs = random.sample(
                leaf_locations, min(random.randint(1, 4), len(leaf_locations))
            )
            for i, loc in enumerate(locs):
                if i == len(locs) - 1:
                    qty = remaining
                else:
                    qty = random.randint(1, max(1, remaining // len(locs)))
                    remaining -= qty
                if qty > 0:
                    inv_loc_objs.append(
                        InventoryLocation(inventory=inv, location=loc, quantity=qty)
                    )
        InventoryLocation.objects.bulk_create(inv_loc_objs, batch_size=BATCH_SIZE)

        # ── 5. Bills of materials ────────────────────────────────
        self._log("Creating bills of materials...")

        # Build cheapest-supplier-cost lookup for realistic BOM costing
        cheapest_cost: dict[int, float] = {}
        for sp in SupplierProduct.objects.all():
            c = float(sp.cost)
            if sp.product_id not in cheapest_cost or c < cheapest_cost[sp.product_id]:
                cheapest_cost[sp.product_id] = c

        num_boms = min(15, len(products))
        sample_prods = random.sample(products, num_boms)
        bom_product_ids: set[int] = set()
        bom_items_to_create = []
        # Track BOM structure in memory for production ledger cost calc
        bom_component_map: dict[
            int, list[tuple[int, int]]
        ] = {}  # product_id → [(comp_id, qty)]
        bom_products_to_reprice: list[tuple] = []  # (prod, material_cost, prod_cost)
        for prod in sample_prods:
            bom_product_ids.add(prod.pk)
            components = [
                p for p in products if p.pk not in bom_product_ids and p != prod
            ]
            n_comps = random.randint(2, min(4, len(components)))
            chosen = random.sample(components, n_comps)
            comp_list = []
            material_cost = Decimal("0")
            for comp in chosen:
                qty = random.randint(1, 3)
                bom_items_to_create.append(
                    BOMItem(bom=None, product=comp, quantity=qty)
                )  # type: ignore[arg-type]
                comp_list.append((comp.pk, qty))
                unit = Decimal(str(cheapest_cost.get(comp.pk, 10.0)))
                material_cost += unit * qty
            bom_component_map[prod.pk] = comp_list
            # production_cost = 10-25% of material cost (labour + overhead)
            prod_cost = round(float(material_cost) * random.uniform(0.10, 0.25), 2)
            bom_products_to_reprice.append((prod, float(material_cost), prod_cost))

        # Create BOMs and back-fill the FK on queued BOMItems
        bom_idx = 0
        for prod, material_cost, prod_cost in bom_products_to_reprice:
            bom = BillOfMaterials.objects.create(
                product=prod,
                production_cost=Decimal(str(prod_cost)),
            )
            n_items = len(bom_component_map[prod.pk])
            for i in range(n_items):
                bom_items_to_create[bom_idx + i].bom = bom
            bom_idx += n_items

            # Set sale_price so margin is 20-40% above total cost
            total_cost = material_cost + prod_cost
            margin = random.uniform(1.20, 1.40)
            prod.sale_price = Decimal(str(round(total_cost * margin, 2)))
            prod.catalogue_item = True

        BOMItem.objects.bulk_create(bom_items_to_create, batch_size=BATCH_SIZE)
        bom_products = [p for p in products if p.pk in bom_product_ids]

        # Persist repriced BOM products
        if bom_products:
            Product.objects.bulk_update(
                bom_products, ["sale_price", "catalogue_item"], batch_size=BATCH_SIZE
            )

        # Update customer prices for BOM products to stay consistent
        bom_prod_sale = {
            p.pk: float(p.sale_price) for p in bom_products if p.sale_price
        }
        cp_updates = []
        for cp in CustomerProduct.objects.filter(product_id__in=bom_prod_sale):
            base = bom_prod_sale[cp.product_id]
            cp.price = Decimal(str(round(base * random.uniform(0.90, 1.10), 2)))
            cp_updates.append(cp)
        if cp_updates:
            CustomerProduct.objects.bulk_update(
                cp_updates, ["price"], batch_size=BATCH_SIZE
            )

        # ── 6. Plan all daily data in memory ─────────────────────
        self._log("Planning daily orders and ledger entries...")

        # Descriptors: (entity, date, ship/due_date, lines)
        so_descriptors: list[tuple] = []
        po_descriptors: list[tuple] = []
        prod_job_list: list[tuple] = []
        ledger_ops: list[tuple[int, int, object]] = []

        inv_quantities = {inv.product_id: inv.quantity for inv in inventories}
        all_product_ids = list(inv_quantities.keys())

        current = start_date
        day = 0
        report_every = max(1, total_days // 10)

        while current < now:
            day += 1
            if day % report_every == 0:
                self._log(f"  day {day}/{total_days} ({day * 100 // total_days}%)")

            weekday = current.weekday()
            is_weekend = weekday >= 5
            so_count = random.randint(0, 1) if is_weekend else random.randint(1, 5)
            po_count = 0 if is_weekend else random.randint(0, 4)
            prod_count = 0 if is_weekend else random.randint(0, 2)

            # ── Purchase orders FIRST (stock flows in) ───────────
            for _ in range(po_count):
                supp = random.choice(suppliers)
                sp_list = supp_prod_map.get(supp.pk, [])
                if not sp_list:
                    continue
                due = (current + timedelta(days=random.randint(7, 45))).date()
                due_passed = due < now.date()
                if due_passed:
                    order_complete = random.random() < 0.97
                else:
                    order_complete = None
                po_lines: list[tuple] = []
                for _ in range(random.randint(1, 4)):
                    sp = random.choice(sp_list)
                    qty = random.randint(10, 100)
                    if order_complete is True:
                        complete = True
                    elif order_complete is False:
                        complete = False
                    else:
                        chance = 0.7 if (now - current).days > 14 else 0.2
                        complete = random.random() < chance
                    received = qty if complete else random.randint(0, qty - 1)
                    store_confirmed = complete and random.random() < 0.95
                    if complete:
                        pid = sp.product_id
                        inv_quantities[pid] = inv_quantities.get(pid, 0) + qty
                    po_lines.append((sp, qty, complete, received, store_confirmed))
                po_descriptors.append((supp, current, due, po_lines))

            # ── Production jobs ──────────────────────────────────
            for _ in range(prod_count):
                if bom_products:
                    prod_product = random.choice(bom_products)
                    due = (current + timedelta(days=random.randint(5, 30))).date()
                    due_passed = due < now.date()
                    qty = random.randint(5, 50)
                    if due_passed:
                        if random.random() < 0.97:
                            received = qty
                        else:
                            received = random.randint(0, qty - 1)
                    elif (now - current).days > 14:
                        received = (
                            qty if random.random() < 0.6 else random.randint(0, qty)
                        )
                    else:
                        received = random.randint(0, qty // 2)
                    complete = received >= qty
                    allocated = True
                    if complete:
                        inv_quantities[prod_product.pk] = (
                            inv_quantities.get(prod_product.pk, 0) + received
                        )
                        comps = bom_component_map.get(prod_product.pk, [])
                        for comp_id, comp_qty in comps:
                            deduction = comp_qty * received
                            inv_quantities[comp_id] = max(
                                inv_quantities.get(comp_id, 0) - deduction, 0
                            )
                    prod_job_list.append(
                        (prod_product, current, due, qty, received, complete, allocated)
                    )

            # ── Sales orders AFTER (stock flows out) ─────────────
            for _ in range(so_count):
                cust = random.choice(customers)
                cp_list = cust_prod_map.get(cust.pk, [])
                if not cp_list:
                    continue
                ship_by = (current + timedelta(days=random.randint(3, 30))).date()
                ship_by_passed = ship_by < now.date()
                if ship_by_passed:
                    order_complete = random.random() < 0.97
                else:
                    order_complete = None
                lines = []
                # Collect stock needs for past-due orders first
                line_specs = []
                for _ in range(random.randint(1, 4)):
                    cp = random.choice(cp_list)
                    qty = random.randint(1, 20)
                    line_specs.append((cp, qty))

                if order_complete is True:
                    # Check if we can fill all lines; if not, create a
                    # restocking purchase so the books balance.
                    for cp, qty in line_specs:
                        pid = cp.product_id
                        shortfall = qty - inv_quantities.get(pid, 0)
                        if shortfall > 0:
                            # Find a supplier for this product
                            restock_sp = None
                            for sp_obj in sp_objs:
                                if sp_obj.product_id == pid:
                                    restock_sp = sp_obj
                                    break
                            if restock_sp:
                                restock_qty = shortfall + random.randint(5, 20)
                                restock_due = (
                                    current - timedelta(days=random.randint(1, 5))
                                ).date()
                                po_descriptors.append(
                                    (
                                        restock_sp.supplier,
                                        current - timedelta(days=random.randint(7, 14)),
                                        restock_due,
                                        [
                                            (
                                                restock_sp,
                                                restock_qty,
                                                True,
                                                restock_qty,
                                                True,
                                            )
                                        ],
                                    )
                                )
                                inv_quantities[pid] = (
                                    inv_quantities.get(pid, 0) + restock_qty
                                )
                            else:
                                # No supplier — just inject stock
                                inv_quantities[pid] = (
                                    inv_quantities.get(pid, 0) + shortfall
                                )

                for cp, qty in line_specs:
                    pid = cp.product_id
                    current_stock = inv_quantities.get(pid, 0)
                    if order_complete is True:
                        complete = True
                    elif order_complete is False:
                        complete = False
                    else:
                        chance = 0.7 if (now - current).days > 14 else 0.2
                        complete = current_stock >= qty and random.random() < chance
                    shipped = qty if complete else random.randint(0, qty - 1)
                    if complete:
                        inv_quantities[pid] = current_stock - qty
                    lines.append((cp, qty, complete, shipped))
                so_descriptors.append((cust, current, ship_by, lines))
            sample_size = random.randint(0, 2)
            if sample_size > 0 and all_product_ids:
                for pid in random.sample(
                    all_product_ids, min(sample_size, len(all_product_ids))
                ):
                    change = random.randint(-5, 5)
                    if change == 0:
                        continue
                    current_qty = inv_quantities.get(pid, 0)
                    new_qty = max(current_qty + change, 0)
                    actual_change = new_qty - current_qty
                    if actual_change == 0:
                        continue
                    inv_quantities[pid] = new_qty
                    ledger_ops.append((pid, actual_change, current))

            current += timedelta(days=1)

        # ── Disable auto_now / auto_now_add on all date fields ───
        auto_date_fields: list[tuple] = []
        for model in (
            InventoryLedger,
            SalesLedger,
            PurchaseLedger,
            ProductionLedger,
            SalesOrder,
            PurchaseOrder,
            Production,
            Inventory,
        ):
            for field in model._meta.get_fields():
                if getattr(field, "auto_now_add", False):
                    auto_date_fields.append((field, "auto_now_add", True))
                    field.auto_now_add = False  # type: ignore[union-attr]
                if getattr(field, "auto_now", False):
                    auto_date_fields.append((field, "auto_now", True))
                    field.auto_now = False  # type: ignore[union-attr]

        try:
            self._bulk_insert_all(
                so_descriptors,
                po_descriptors,
                prod_job_list,
                ledger_ops,
                inv_quantities,
                bom_component_map,
            )
        finally:
            for field, attr, orig in auto_date_fields:
                setattr(field, attr, orig)

        # ── Sync final inventory quantities ──────────────────────
        self._log("Syncing final inventory quantities...")
        inv_updates = []
        for inv in Inventory.objects.all():
            target = inv_quantities.get(inv.product_id)
            if target is not None and inv.quantity != target:
                inv.quantity = target
                inv_updates.append(inv)
        if inv_updates:
            Inventory.objects.bulk_update(
                inv_updates, ["quantity"], batch_size=BATCH_SIZE
            )

        # ── Rebuild cached totals ────────────────────────────────
        self._log("Rebuilding cached order totals...")
        SalesOrder.objects.update(
            total_amount_cached=Subquery(
                SalesOrderLine.objects.filter(sales_order=OuterRef("pk"))
                .values("sales_order")
                .annotate(total=Sum(F("product__price") * F("quantity")))
                .values("total")[:1]
            )
        )
        SalesOrder.objects.filter(total_amount_cached__isnull=True).update(
            total_amount_cached=Decimal("0.00")
        )
        PurchaseOrder.objects.update(
            total_amount_cached=Subquery(
                PurchaseOrderLine.objects.filter(purchase_order=OuterRef("pk"))
                .values("purchase_order")
                .annotate(total=Sum(F("product__cost") * F("quantity")))
                .values("total")[:1]
            )
        )
        PurchaseOrder.objects.filter(total_amount_cached__isnull=True).update(
            total_amount_cached=Decimal("0.00")
        )

        # ── Rebuild inventory caches ─────────────────────────────
        self._log("Rebuilding inventory required cache...")
        for inv in Inventory.objects.all():
            inv.update_required_cached()

        # ── Rebuild production allocations ───────────────────────
        self._log("Rebuilding production allocations...")
        ProductionAllocated.objects.all().update(quantity=0)
        open_jobs = Production.objects.filter(
            closed=False, bom_allocated=True
        ).select_related("product")
        for job in open_jobs:
            comps = bom_component_map.get(job.product_id, [])
            for comp_id, comp_qty in comps:
                alloc_qty = comp_qty * job.quantity
                ProductionAllocated.objects.filter(product_id=comp_id).update(
                    quantity=F("quantity") + alloc_qty
                )

        # ── Refresh finance dashboard cache ──────────────────────
        self._log("Refreshing finance dashboard cache...")
        refresh_finance_dashboard_cache()

    # ------------------------------------------------------------------
    def _bulk_insert_all(
        self,
        so_descriptors,
        po_descriptors,
        prod_job_list,
        ledger_ops,
        inv_quantities,
        bom_component_map,
    ):
        """Create all orders, lines, and ledger entries with correct dates.

        Called AFTER auto_now / auto_now_add have been temporarily disabled
        so that every date field receives its historical value.
        """
        # ── Sales orders + lines ─────────────────────────────────
        self._log(f"Creating {len(so_descriptors)} sales orders...")
        so_objs = [
            SalesOrder(
                customer=cust,
                created_at=dt,
                updated_at=dt,
                ship_by_date=ship_by,
            )
            for cust, dt, ship_by, _ in so_descriptors
        ]
        SalesOrder.objects.bulk_create(so_objs, batch_size=BATCH_SIZE)

        sol_objs = []
        sales_ledger_objs = []
        sales_inv_ledger_objs = []
        for so, (cust, dt, _ship_by, lines) in zip(so_objs, so_descriptors):
            for cp, qty, complete, shipped in lines:
                value = cp.price * qty
                sol_objs.append(
                    SalesOrderLine(
                        sales_order=so,
                        product=cp,
                        quantity=qty,
                        quantity_shipped=shipped,
                        complete=complete,
                        closed=complete,
                        value=value,
                    )
                )
                if complete:
                    sales_ledger_objs.append(
                        SalesLedger(
                            product=cp.product,
                            quantity=qty,
                            customer=cust,
                            value=value,
                            date=dt,
                            transaction_id=so.pk,
                        )
                    )
                    sales_inv_ledger_objs.append(
                        InventoryLedger(
                            product=cp.product,
                            quantity=-abs(qty),
                            action=InventoryLedger.Action.SALES_ORDER,
                            transaction_id=so.pk,
                            date=dt,
                        )
                    )
        self._log(f"Creating {len(sol_objs)} sales order lines...")
        SalesOrderLine.objects.bulk_create(sol_objs, batch_size=BATCH_SIZE)

        # ── Purchase orders + lines ──────────────────────────────
        self._log(f"Creating {len(po_descriptors)} purchase orders...")
        po_objs = [
            PurchaseOrder(
                supplier=supp,
                created_at=dt,
                updated_at=dt,
                due_date=due,
            )
            for supp, dt, due, _ in po_descriptors
        ]
        PurchaseOrder.objects.bulk_create(po_objs, batch_size=BATCH_SIZE)

        pol_objs = []
        purchase_ledger_objs = []
        purchase_inv_ledger_objs = []
        for po, (supp, dt, _due, lines) in zip(po_objs, po_descriptors):
            for sp, qty, complete, received, store_confirmed in lines:
                value = sp.cost * qty
                pol_objs.append(
                    PurchaseOrderLine(
                        purchase_order=po,
                        product=sp,
                        quantity=qty,
                        quantity_received=received,
                        complete=complete,
                        closed=complete,
                        value=value,
                        store_confirmed=store_confirmed,
                        store_confirmed_at=dt if store_confirmed else None,
                    )
                )
                if complete:
                    purchase_ledger_objs.append(
                        PurchaseLedger(
                            product=sp.product,
                            quantity=qty,
                            supplier=supp,
                            value=value,
                            date=dt,
                            transaction_id=po.pk,
                        )
                    )
                    purchase_inv_ledger_objs.append(
                        InventoryLedger(
                            product=sp.product,
                            quantity=qty,
                            action=InventoryLedger.Action.PURCHASE_ORDER,
                            transaction_id=po.pk,
                            date=dt,
                        )
                    )
        self._log(f"Creating {len(pol_objs)} purchase order lines...")
        PurchaseOrderLine.objects.bulk_create(pol_objs, batch_size=BATCH_SIZE)

        # ── Production jobs + ledger ─────────────────────────────
        self._log(f"Creating {len(prod_job_list)} production jobs...")
        prod_objs = [
            Production(
                product=prod,
                quantity=qty,
                quantity_received=received,
                complete=complete,
                closed=complete,
                bom_allocated=allocated,
                bom_allocated_amount=qty if allocated else None,
                due_date=due,
                created_at=dt,
                updated_at=dt,
            )
            for prod, dt, due, qty, received, complete, allocated in prod_job_list
        ]
        Production.objects.bulk_create(prod_objs, batch_size=BATCH_SIZE)

        # Production ledger entries for completed jobs
        prod_ledger_objs = []
        prod_inv_ledger_objs = []
        for job_obj, (prod, dt, _due, qty, received, complete, _alloc) in zip(
            prod_objs, prod_job_list
        ):
            if received > 0:
                unit_cost = float(prod.sale_price) * 0.4 if prod.sale_price else 10.0
                prod_ledger_objs.append(
                    ProductionLedger(
                        product=prod,
                        quantity=received,
                        value=Decimal(str(round(unit_cost * received, 2))),
                        date=dt,
                        transaction_id=job_obj.pk,
                    )
                )
                prod_inv_ledger_objs.append(
                    InventoryLedger(
                        product=prod,
                        quantity=received,
                        action=InventoryLedger.Action.PRODUCTION,
                        transaction_id=job_obj.pk,
                        date=dt,
                    )
                )
                # Component deductions
                comps = bom_component_map.get(prod.pk, [])
                for comp_id, comp_qty in comps:
                    prod_inv_ledger_objs.append(
                        InventoryLedger(
                            product_id=comp_id,
                            quantity=-abs(comp_qty * received),
                            action=InventoryLedger.Action.PRODUCTION,
                            transaction_id=job_obj.pk,
                            date=dt,
                        )
                    )

        if prod_ledger_objs:
            self._log(f"Creating {len(prod_ledger_objs)} production ledger entries...")
            ProductionLedger.objects.bulk_create(
                prod_ledger_objs, batch_size=BATCH_SIZE
            )

        # ── All inventory ledger entries ─────────────────────────
        all_inv_ledger = [
            InventoryLedger(
                product_id=pid,
                quantity=change,
                action=InventoryLedger.Action.SEED,
                transaction_id=0,
                date=dt,
            )
            for pid, change, dt in ledger_ops
        ]
        all_inv_ledger.extend(sales_inv_ledger_objs)
        all_inv_ledger.extend(purchase_inv_ledger_objs)
        all_inv_ledger.extend(prod_inv_ledger_objs)
        self._log(f"Creating {len(all_inv_ledger)} inventory ledger entries...")
        InventoryLedger.objects.bulk_create(all_inv_ledger, batch_size=BATCH_SIZE)

        self._log(f"Creating {len(sales_ledger_objs)} sales ledger entries...")
        SalesLedger.objects.bulk_create(sales_ledger_objs, batch_size=BATCH_SIZE)

        self._log(f"Creating {len(purchase_ledger_objs)} purchase ledger entries...")
        PurchaseLedger.objects.bulk_create(purchase_ledger_objs, batch_size=BATCH_SIZE)
