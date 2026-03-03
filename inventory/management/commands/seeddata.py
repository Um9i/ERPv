import random
import time
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F, Sum, OuterRef, Subquery
from django.utils import timezone

from inventory.models import Inventory, InventoryLedger, Product
from production.models import BillOfMaterials, BOMItem, Production
from procurement.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseLedger,
    Supplier,
    SupplierContact,
    SupplierProduct,
)
from sales.models import (
    Customer,
    CustomerContact,
    CustomerProduct,
    SalesOrder,
    SalesOrderLine,
    SalesLedger,
)
from main.factories import CustomerFactory, SupplierFactory, ProductFactory

from faker import Faker

fake = Faker()

BATCH_SIZE = 500


class Command(BaseCommand):
    help = "Seed the database with generated data (optimized for speed)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--years",
            type=int,
            default=2,
            help="Number of years of history to generate (default 2)",
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
        years = options["years"]
        num_customers = options["customers"]
        num_suppliers = options["suppliers"]
        num_products = options["products"]

        start_date = timezone.now() - timedelta(days=365 * years)
        now = timezone.now()
        total_days = (now - start_date).days

        self.stdout.write(
            f"Seeding {years} years ({total_days} days) from {start_date.date()}..."
        )
        t0 = time.monotonic()

        with transaction.atomic():
            self._seed(start_date, now, total_days, num_customers, num_suppliers, num_products)

        elapsed = time.monotonic() - t0
        self.stdout.write(self.style.SUCCESS(f"Seeding complete in {elapsed:.1f}s"))

    # ------------------------------------------------------------------
    def _log(self, msg):
        self.stdout.write(f"  {msg}")

    # ------------------------------------------------------------------
    def _seed(self, start_date, now, total_days, num_customers, num_suppliers, num_products):
        # ── 1. Base entities (small counts – factories are fine) ──
        self._log("Creating products...")
        products = ProductFactory.create_batch(num_products)

        self._log("Creating customers...")
        customers = CustomerFactory.create_batch(num_customers)

        self._log("Creating suppliers...")
        suppliers = SupplierFactory.create_batch(num_suppliers)

        # ── 1b. Create contacts for customers and suppliers ────
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

        # ── 2. Link products ↔ customers / suppliers (bulk) ──────
        self._log("Linking customer ↔ product relationships...")
        cp_objs = []
        for cust in customers:
            n = random.randint(3, min(10, len(products)))
            for prod in random.sample(products, n):
                cp_objs.append(
                    CustomerProduct(
                        customer=cust,
                        product=prod,
                        price=Decimal(str(round(random.uniform(5, 500), 2))),
                    )
                )
        CustomerProduct.objects.bulk_create(cp_objs, batch_size=BATCH_SIZE)

        # In-memory lookup: customer_id → [CustomerProduct, ...]
        cust_prod_map = defaultdict(list)
        for cp in CustomerProduct.objects.select_related("customer", "product"):
            cust_prod_map[cp.customer_id].append(cp)

        self._log("Linking supplier ↔ product relationships...")
        sp_objs = []
        seen_sp = set()
        for supp in suppliers:
            n = random.randint(3, min(10, len(products)))
            for prod in random.sample(products, n):
                key = (supp.pk, prod.pk)
                if key in seen_sp:
                    continue
                seen_sp.add(key)
                sp_objs.append(
                    SupplierProduct(
                        supplier=supp,
                        product=prod,
                        cost=Decimal(str(round(random.uniform(1, 200), 2))),
                    )
                )
        SupplierProduct.objects.bulk_create(sp_objs, batch_size=BATCH_SIZE)

        supp_prod_map = defaultdict(list)
        for sp in SupplierProduct.objects.select_related("supplier", "product"):
            supp_prod_map[sp.supplier_id].append(sp)

        # ── 3. Set random starting inventory quantities ──────────
        # Product post_save signal already created Inventory rows via factories.
        self._log("Setting initial inventory quantities...")
        inventories = list(Inventory.objects.all())
        for inv in inventories:
            inv.quantity = random.randint(0, 200)
        Inventory.objects.bulk_update(inventories, ["quantity"], batch_size=BATCH_SIZE)

        # ── 4. Bills of materials ────────────────────────────────
        self._log("Creating bills of materials...")
        sample_prods = random.sample(products, min(10, len(products)))
        bom_product_ids = set()
        bom_items_to_create = []
        for prod in sample_prods:
            bom = BillOfMaterials.objects.create(product=prod)
            bom_product_ids.add(prod.pk)
            components = [p for p in products if p != prod]
            for comp in random.sample(components, min(2, len(components))):
                bom_items_to_create.append(
                    BOMItem(bom=bom, product=comp, quantity=random.randint(1, 5))
                )
        BOMItem.objects.bulk_create(bom_items_to_create, batch_size=BATCH_SIZE)
        bom_products = [p for p in products if p.pk in bom_product_ids]

        # ── 5. Plan all daily data in memory (no DB queries) ─────
        self._log("Planning daily orders and ledger entries...")

        so_descriptors = []   # [(customer, date, [(cp, qty, complete, shipped), ...])]
        po_descriptors = []   # [(supplier, date, [(sp, qty, complete, received), ...])]
        prod_job_list = []    # [(product, date)]
        ledger_ops = []       # [(product_id, change, date)]

        # Track inventory quantities in Python for ledger simulation
        inv_quantities = {inv.product_id: inv.quantity for inv in inventories}
        all_product_ids = list(inv_quantities.keys())

        current = start_date
        day = 0
        report_every = max(1, total_days // 10)

        while current < now:
            day += 1
            if day % report_every == 0:
                self._log(f"  day {day}/{total_days} ({day * 100 // total_days}%)")

            # Sales orders
            for _ in range(random.randint(0, 5)):
                cust = random.choice(customers)
                cp_list = cust_prod_map.get(cust.pk, [])
                if not cp_list:
                    continue
                lines = []
                for _ in range(random.randint(1, 3)):
                    cp = random.choice(cp_list)
                    qty = random.randint(1, 20)
                    # Only allow completion if we have enough stock
                    pid = cp.product_id
                    current_stock = inv_quantities.get(pid, 0)
                    if current_stock >= qty:
                        complete = random.choice([True, False])
                    else:
                        complete = False
                    shipped = random.randint(0, qty)
                    if complete:
                        # Track the inventory deduction from completed sales
                        inv_quantities[pid] = current_stock - qty
                    lines.append((cp, qty, complete, shipped))
                so_descriptors.append((cust, current, lines))

            # Purchase orders
            for _ in range(random.randint(0, 3)):
                supp = random.choice(suppliers)
                sp_list = supp_prod_map.get(supp.pk, [])
                if not sp_list:
                    continue
                lines = []
                for _ in range(random.randint(1, 3)):
                    sp = random.choice(sp_list)
                    qty = random.randint(1, 50)
                    complete = random.choice([True, False])
                    received = random.randint(0, qty)
                    if complete:
                        # Track the inventory addition from completed purchases
                        pid = sp.product_id
                        inv_quantities[pid] = inv_quantities.get(pid, 0) + qty
                    lines.append((sp, qty, complete, received))
                po_descriptors.append((supp, current, lines))

            # Production jobs (only products with BOMs)
            for _ in range(random.randint(0, 2)):
                if bom_products:
                    prod_job_list.append(
                        (random.choice(bom_products), current)
                    )

            # Inventory ledger entries (random adjustments)
            sample_size = random.randint(0, 3)
            if sample_size > 0 and all_product_ids:
                for pid in random.sample(
                    all_product_ids, min(sample_size, len(all_product_ids))
                ):
                    change = random.randint(-10, 10)
                    if change == 0:
                        continue
                    current_qty = inv_quantities.get(pid, 0)
                    # Clamp so stock never goes negative
                    new_qty = max(current_qty + change, 0)
                    actual_change = new_qty - current_qty
                    if actual_change == 0:
                        continue
                    inv_quantities[pid] = new_qty
                    ledger_ops.append((pid, actual_change, current))

            current += timedelta(days=1)

        # ── Disable auto_now / auto_now_add on all date fields ───
        # This must happen BEFORE constructing objects so that Django
        # does not silently replace historical dates with now().
        auto_date_fields = []
        for model in (InventoryLedger, SalesLedger, PurchaseLedger,
                       SalesOrder, PurchaseOrder, Production, Inventory):
            for field in model._meta.get_fields():
                if getattr(field, "auto_now_add", False):
                    auto_date_fields.append((field, "auto_now_add", True))
                    field.auto_now_add = False
                if getattr(field, "auto_now", False):
                    auto_date_fields.append((field, "auto_now", True))
                    field.auto_now = False

        try:
            self._bulk_insert_all(
                so_descriptors, po_descriptors, prod_job_list,
                ledger_ops, inv_quantities,
            )
        finally:
            for field, attr, orig in auto_date_fields:
                setattr(field, attr, orig)

        # ── 10. Sync final inventory quantities ──────────────────
        self._log("Syncing final inventory quantities...")
        inv_updates = []
        for inv in Inventory.objects.all():
            target = inv_quantities.get(inv.product_id)
            if target is not None and inv.quantity != target:
                inv.quantity = target
                inv_updates.append(inv)
        if inv_updates:
            Inventory.objects.bulk_update(inv_updates, ["quantity"], batch_size=BATCH_SIZE)

        # ── 11. Rebuild cached totals (single pass) ──────────────
        self._log("Rebuilding cached order totals...")
        # Sales order totals
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
        # Purchase order totals
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

        # Rebuild required_cached on inventory rows
        self._log("Rebuilding inventory required cache...")
        for inv in Inventory.objects.all():
            inv.update_required_cached()

    # ------------------------------------------------------------------
    def _bulk_insert_all(self, so_descriptors, po_descriptors, prod_job_list,
                         ledger_ops, inv_quantities):
        """Create all orders, lines, and ledger entries with correct dates.

        Called AFTER auto_now / auto_now_add have been temporarily disabled
        so that every date field receives its historical value.
        """
        # ── 6. Sales orders + lines ──────────────────────────────
        self._log(f"Creating {len(so_descriptors)} sales orders...")
        so_objs = [
            SalesOrder(customer=cust, created_at=dt, updated_at=dt)
            for cust, dt, _ in so_descriptors
        ]
        SalesOrder.objects.bulk_create(so_objs, batch_size=BATCH_SIZE)

        sol_objs = []
        sales_ledger_objs = []
        sales_inv_ledger_objs = []
        for so, (cust, dt, lines) in zip(so_objs, so_descriptors):
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
                            action="Sales Order",
                            transaction_id=so.pk,
                            date=dt,
                        )
                    )
        self._log(f"Creating {len(sol_objs)} sales order lines...")
        SalesOrderLine.objects.bulk_create(sol_objs, batch_size=BATCH_SIZE)

        # ── 7. Purchase orders + lines ───────────────────────────
        self._log(f"Creating {len(po_descriptors)} purchase orders...")
        po_objs = [
            PurchaseOrder(supplier=supp, created_at=dt, updated_at=dt)
            for supp, dt, _ in po_descriptors
        ]
        PurchaseOrder.objects.bulk_create(po_objs, batch_size=BATCH_SIZE)

        pol_objs = []
        purchase_ledger_objs = []
        purchase_inv_ledger_objs = []
        for po, (supp, dt, lines) in zip(po_objs, po_descriptors):
            for sp, qty, complete, received in lines:
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
                            action="Purchase Order",
                            transaction_id=po.pk,
                            date=dt,
                        )
                    )
        self._log(f"Creating {len(pol_objs)} purchase order lines...")
        PurchaseOrderLine.objects.bulk_create(pol_objs, batch_size=BATCH_SIZE)

        # ── 8. Production jobs ───────────────────────────────────
        self._log(f"Creating {len(prod_job_list)} production jobs...")
        Production.objects.bulk_create(
            [
                Production(
                    product=prod,
                    quantity=random.randint(1, 100),
                    quantity_received=0,
                    complete=False,
                    closed=False,
                    bom_allocated=False,
                    created_at=dt,
                    updated_at=dt,
                )
                for prod, dt in prod_job_list
            ],
            batch_size=BATCH_SIZE,
        )

        # ── 9. All ledger entries ────────────────────────────────
        all_inv_ledger = [
            InventoryLedger(
                product_id=pid,
                quantity=change,
                action="Seed",
                transaction_id=0,
                date=dt,
            )
            for pid, change, dt in ledger_ops
        ]
        all_inv_ledger.extend(sales_inv_ledger_objs)
        all_inv_ledger.extend(purchase_inv_ledger_objs)
        self._log(f"Creating {len(all_inv_ledger)} inventory ledger entries...")
        InventoryLedger.objects.bulk_create(all_inv_ledger, batch_size=BATCH_SIZE)

        self._log(f"Creating {len(sales_ledger_objs)} sales ledger entries...")
        SalesLedger.objects.bulk_create(sales_ledger_objs, batch_size=BATCH_SIZE)

        self._log(f"Creating {len(purchase_ledger_objs)} purchase ledger entries...")
        PurchaseLedger.objects.bulk_create(purchase_ledger_objs, batch_size=BATCH_SIZE)
