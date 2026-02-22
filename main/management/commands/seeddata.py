import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from main.factories import (
    CustomerFactory,
    SupplierFactory,
    ProductFactory,
    InventoryFactory,
    CustomerProductFactory,
    SupplierProductFactory,
    SalesOrderFactory,
    SalesOrderLineFactory,
    PurchaseOrderFactory,
    PurchaseOrderLineFactory,
    BillOfMaterialsFactory,
    BOMItemFactory,
    ProductionFactory,
)


class Command(BaseCommand):
    help = "Seed the database with a couple of years of generated data."

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
        self.stdout.write(f"seeding {years} years starting {start_date.date()}...")

        # create base entities
        products = ProductFactory.create_batch(num_products)
        customers = CustomerFactory.create_batch(num_customers)
        suppliers = SupplierFactory.create_batch(num_suppliers)

        # link customers and suppliers to random products
        for customer in customers:
            for _ in range(random.randint(3, 10)):
                CustomerProductFactory(customer=customer, product=random.choice(products))
        for supplier in suppliers:
            for _ in range(random.randint(3, 10)):
                SupplierProductFactory(supplier=supplier, product=random.choice(products))

        # set up inventories
        for product in products:
            InventoryFactory(product=product)

        # create some BOMs for a subset of products so production can allocate
        sample_prods = random.sample(products, min(10, len(products)))
        for prod in sample_prods:
            bom = BillOfMaterialsFactory(product=prod)
            # attach a couple of component items that are not the finished prod
            components = [p for p in products if p != prod]
            for _ in range(2):
                if components:
                    BOMItemFactory(bom=bom, product=random.choice(components))

        # iterate through each day and create orders/jobs
        current = start_date
        while current < timezone.now():
            # sales orders
            for _ in range(random.randint(0, 5)):
                cust = random.choice(customers)
                so = SalesOrderFactory(customer=cust, created_at=current)
                # add 1-3 lines to the order
                for _ in range(random.randint(1, 3)):
                    if cust.customer_products.exists():
                        cp = random.choice(list(cust.customer_products.all()))
                    else:
                        cp = CustomerProductFactory(customer=cust, product=random.choice(products))
                    qty = random.randint(1, 20)
                    sol = SalesOrderLineFactory(
                        sales_order=so,
                        product=cp,
                        quantity=qty,
                        complete=random.choice([True, False]),
                        quantity_shipped=random.randint(0, qty),
                    )
                so.update_cached_total()

            # purchase orders
            for _ in range(random.randint(0, 3)):
                supp = random.choice(suppliers)
                po = PurchaseOrderFactory(supplier=supp, created_at=current)
                for _ in range(random.randint(1, 3)):
                    if supp.supplier_products.exists():
                        sp = random.choice(list(supp.supplier_products.all()))
                    else:
                        sp = SupplierProductFactory(supplier=supp, product=random.choice(products))
                    qty = random.randint(1, 50)
                    PurchaseOrderLineFactory(
                        purchase_order=po,
                        product=sp,
                        quantity=qty,
                        complete=random.choice([True, False]),
                        quantity_received=random.randint(0, qty),
                    )
                po.update_cached_total()

            # production jobs (only for products that have BOMs)
            for _ in range(random.randint(0, 2)):
                possible = [p for p in products if hasattr(p, 'billofmaterials')]
                if possible:
                    prod = random.choice(possible)
                    ProductionFactory(product=prod, created_at=current)

            # add a few inventory ledger entries dated to this day to build history
            from inventory.models import Inventory, InventoryLedger
            for inv in Inventory.objects.order_by('?')[: random.randint(0, 3)]:
                change = random.randint(-10, 10)
                if change == 0:
                    continue
                # adjust quantity but never go negative
                newqty = max(inv.quantity + change, 0)
                inv.quantity = newqty
                inv.save(update_fields=['quantity'])
                InventoryLedger.objects.create(
                    product=inv.product,
                    quantity=change,
                    action='Seed',
                    transaction_id=0,
                    date=current,
                )

            # advance one day
            current += timedelta(days=1)

        self.stdout.write(self.style.SUCCESS("seeding complete"))
