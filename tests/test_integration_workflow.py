"""Integration tests for full order-to-shipment-to-ledger workflows.

These tests trace complete cross-module flows, verifying that inventory,
ledger entries, and financial records stay consistent from procurement
through production to sales.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from inventory.models import Inventory, InventoryLedger, Product
from inventory.services import (
    refresh_required_cache_for_products,
)
from procurement.models import (
    PurchaseLedger,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierProduct,
)
from procurement.services import receive_purchase_order_line
from production.models import BillOfMaterials, BOMItem, Production
from sales.models import (
    Customer,
    CustomerProduct,
    SalesLedger,
    SalesOrder,
    SalesOrderLine,
)


@pytest.fixture
def user(db):
    return User.objects.create_user(username="integration", password="pass")


@pytest.mark.django_db
class TestProcurementToLedger:
    """Purchase order → receive → inventory + purchase ledger."""

    def test_full_receive_updates_inventory_and_ledger(self):
        product = Product.objects.create(name="Widget A")
        supplier = Supplier.objects.create(name="Acme Supplies")
        sp = SupplierProduct.objects.create(supplier=supplier, product=product, cost=25)
        po = PurchaseOrder.objects.create(supplier=supplier)
        line = PurchaseOrderLine.objects.create(
            purchase_order=po, product=sp, quantity=100
        )

        inv = Inventory.objects.get(product=product)
        assert inv.quantity == 0

        # receive entire order
        pid = receive_purchase_order_line(line, 100)
        assert pid == product.pk

        inv.refresh_from_db()
        assert inv.quantity == 100

        line.refresh_from_db()
        assert line.complete is True
        assert line.closed is True
        assert line.value == 25 * 100

        # inventory ledger: one entry, positive qty
        ledger = InventoryLedger.objects.filter(
            product=product, action="Purchase Order"
        )
        assert ledger.count() == 1
        assert ledger.first().quantity == 100

        # purchase ledger
        pl = PurchaseLedger.objects.filter(product=product, transaction_id=po.pk)
        assert pl.count() == 1
        assert pl.first().quantity == 100
        assert pl.first().value == 25 * 100
        assert pl.first().supplier == supplier

    def test_partial_receive_then_complete(self):
        product = Product.objects.create(name="Widget B")
        supplier = Supplier.objects.create(name="Beta Supplies")
        sp = SupplierProduct.objects.create(supplier=supplier, product=product, cost=10)
        po = PurchaseOrder.objects.create(supplier=supplier)
        line = PurchaseOrderLine.objects.create(
            purchase_order=po, product=sp, quantity=50
        )

        # receive 30 of 50
        receive_purchase_order_line(line, 30)
        line.refresh_from_db()
        assert line.quantity_received == 30
        assert line.complete is False
        assert line.closed is False

        inv = Inventory.objects.get(product=product)
        assert inv.quantity == 30

        # receive remaining 20
        receive_purchase_order_line(line, 20)
        line.refresh_from_db()
        assert line.quantity_received == 50
        assert line.complete is True
        assert line.closed is True

        inv.refresh_from_db()
        assert inv.quantity == 50

        # two inventory ledger entries
        assert (
            InventoryLedger.objects.filter(
                product=product, action="Purchase Order"
            ).count()
            == 2
        )

        # two purchase ledger entries
        pls = PurchaseLedger.objects.filter(product=product).order_by("pk")
        assert pls.count() == 2
        assert pls[0].value == 10 * 30
        assert pls[1].value == 10 * 20

    def test_receive_via_view(self, client, user):
        """Full HTTP flow: POST to receive view updates everything."""
        product = Product.objects.create(name="Widget C")
        supplier = Supplier.objects.create(name="Gamma Supplies")
        sp = SupplierProduct.objects.create(supplier=supplier, product=product, cost=5)
        po = PurchaseOrder.objects.create(supplier=supplier)
        line = PurchaseOrderLine.objects.create(
            purchase_order=po, product=sp, quantity=10
        )

        client.force_login(user)
        resp = client.post(
            reverse("procurement:purchase-order-receive", args=[po.pk]),
            {"receive_all": "1"},
        )
        assert resp.status_code == 302

        inv = Inventory.objects.get(product=product)
        assert inv.quantity == 10

        line.refresh_from_db()
        assert line.complete is True
        assert PurchaseLedger.objects.filter(product=product).exists()
        assert InventoryLedger.objects.filter(
            product=product, action="Purchase Order"
        ).exists()


@pytest.mark.django_db
class TestSalesToLedger:
    """Sales order → ship → inventory + sales ledger."""

    def test_full_ship_updates_inventory_and_ledger(self, client, user):
        product = Product.objects.create(name="Gadget X")
        Inventory.objects.filter(product=product).update(quantity=50)
        customer = Customer.objects.create(name="Buyer Inc")
        cp = CustomerProduct.objects.create(
            customer=customer, product=product, price=30
        )
        so = SalesOrder.objects.create(customer=customer)
        line = SalesOrderLine.objects.create(sales_order=so, product=cp, quantity=20)

        client.force_login(user)
        resp = client.post(
            reverse("sales:sales-order-ship", args=[so.pk]),
            {"ship_all": "1"},
        )
        assert resp.status_code == 302

        inv = Inventory.objects.get(product=product)
        assert inv.quantity == 30  # 50 - 20

        line.refresh_from_db()
        assert line.complete is True
        assert line.closed is True
        assert line.quantity_shipped == 20

        # inventory ledger: negative entry
        il = InventoryLedger.objects.filter(product=product, action="Sales Order")
        assert il.count() == 1
        assert il.first().quantity == -20

        # sales ledger: positive entry
        sl = SalesLedger.objects.filter(product=product, transaction_id=so.pk)
        assert sl.count() == 1
        assert sl.first().quantity == 20
        assert sl.first().value == 30 * 20
        assert sl.first().customer == customer

    def test_partial_ship_then_complete(self, client, user):
        product = Product.objects.create(name="Gadget Y")
        Inventory.objects.filter(product=product).update(quantity=100)
        customer = Customer.objects.create(name="Partial Buyer")
        cp = CustomerProduct.objects.create(
            customer=customer, product=product, price=15
        )
        so = SalesOrder.objects.create(customer=customer)
        line = SalesOrderLine.objects.create(sales_order=so, product=cp, quantity=40)

        client.force_login(user)

        # ship 25 of 40
        resp = client.post(
            reverse("sales:sales-order-ship", args=[so.pk]),
            {f"shipped_{line.pk}": "25"},
        )
        assert resp.status_code == 302

        line.refresh_from_db()
        assert line.quantity_shipped == 25
        assert line.complete is False

        inv = Inventory.objects.get(product=product)
        assert inv.quantity == 75

        # ship remaining 15
        resp = client.post(
            reverse("sales:sales-order-ship", args=[so.pk]),
            {f"shipped_{line.pk}": "15"},
        )
        assert resp.status_code == 302

        line.refresh_from_db()
        assert line.quantity_shipped == 40
        assert line.complete is True
        assert line.closed is True

        inv.refresh_from_db()
        assert inv.quantity == 60

        # two of each ledger entry
        assert (
            InventoryLedger.objects.filter(
                product=product, action="Sales Order"
            ).count()
            == 2
        )
        assert SalesLedger.objects.filter(product=product).count() == 2

    def test_ship_rejects_insufficient_stock(self, client, user):
        product = Product.objects.create(name="Gadget Z")
        Inventory.objects.filter(product=product).update(quantity=3)
        customer = Customer.objects.create(name="Greedy Buyer")
        cp = CustomerProduct.objects.create(
            customer=customer, product=product, price=10
        )
        so = SalesOrder.objects.create(customer=customer)
        line = SalesOrderLine.objects.create(sales_order=so, product=cp, quantity=10)

        client.force_login(user)
        resp = client.post(
            reverse("sales:sales-order-ship", args=[so.pk]),
            {f"shipped_{line.pk}": "10"},
        )
        # should re-render with errors, not redirect
        assert resp.status_code == 200
        assert b"Not enough inventory" in resp.content

        # nothing should have changed
        inv = Inventory.objects.get(product=product)
        assert inv.quantity == 3
        assert SalesLedger.objects.filter(product=product).count() == 0


@pytest.mark.django_db
class TestProductionToLedger:
    """BOM allocation → production receive → inventory + ledger."""

    def test_produce_finished_product_from_components(self):
        from production.services import allocate_production, receive_production

        # set up a product with a BOM
        comp1 = Product.objects.create(name="Steel Rod")
        comp2 = Product.objects.create(name="Plastic Cap")
        finished = Product.objects.create(name="Assembled Widget")

        Inventory.objects.filter(product=comp1).update(quantity=200)
        Inventory.objects.filter(product=comp2).update(quantity=300)

        bom = BillOfMaterials.objects.create(product=finished)
        BOMItem.objects.create(bom=bom, product=comp1, quantity=2)
        BOMItem.objects.create(bom=bom, product=comp2, quantity=3)

        job = Production.objects.create(product=finished, quantity=10)

        # allocate materials
        allocate_production(job)
        assert job.bom_allocated is True

        # receive the production
        affected = receive_production(job, 10)
        assert finished.pk in affected
        assert comp1.pk in affected
        assert comp2.pk in affected

        # finished product inventory increased
        inv_finished = Inventory.objects.get(product=finished)
        assert inv_finished.quantity == 10

        # component inventories decreased
        assert Inventory.objects.get(product=comp1).quantity == 180  # 200 - 2*10
        assert Inventory.objects.get(product=comp2).quantity == 270  # 300 - 3*10

        # ledger entries: one positive for finished, two negative for components
        assert InventoryLedger.objects.filter(
            product=finished, action="Production", quantity=10
        ).exists()
        assert InventoryLedger.objects.filter(
            product=comp1, action="Production", quantity=-20
        ).exists()
        assert InventoryLedger.objects.filter(
            product=comp2, action="Production", quantity=-30
        ).exists()


@pytest.mark.django_db
class TestFullCycle:
    """End-to-end: procure → produce → sell → verify all ledgers."""

    def test_procure_produce_sell_cycle(self, client, user):
        # --- 1. Set up products ---
        raw_material = Product.objects.create(name="Raw Material")
        finished_product = Product.objects.create(name="Finished Product")

        # BOM: 5 units of raw_material → 1 finished_product
        bom = BillOfMaterials.objects.create(product=finished_product)
        BOMItem.objects.create(bom=bom, product=raw_material, quantity=5)

        # --- 2. Procure raw materials ---
        supplier = Supplier.objects.create(name="Raw Supplier")
        sp = SupplierProduct.objects.create(
            supplier=supplier, product=raw_material, cost=2
        )
        po = PurchaseOrder.objects.create(supplier=supplier)
        po_line = PurchaseOrderLine.objects.create(
            purchase_order=po, product=sp, quantity=100
        )

        # receive all raw materials
        receive_purchase_order_line(po_line, 100)
        refresh_required_cache_for_products([raw_material.pk])

        inv_raw = Inventory.objects.get(product=raw_material)
        assert inv_raw.quantity == 100

        # purchase ledger recorded
        assert PurchaseLedger.objects.filter(product=raw_material).exists()

        # --- 3. Produce finished goods ---
        from production.services import allocate_production, receive_production

        job = Production.objects.create(product=finished_product, quantity=10)
        allocate_production(job)
        affected = receive_production(job, 10)
        refresh_required_cache_for_products(affected)

        inv_finished = Inventory.objects.get(product=finished_product)
        assert inv_finished.quantity == 10  # 10 produced
        inv_raw.refresh_from_db()
        assert inv_raw.quantity == 50  # 100 - 5*10

        # production ledger entries exist
        assert InventoryLedger.objects.filter(
            product=finished_product, action="Production"
        ).exists()

        # --- 4. Sell finished goods ---
        customer = Customer.objects.create(name="End Customer")
        cp = CustomerProduct.objects.create(
            customer=customer, product=finished_product, price=50
        )
        so = SalesOrder.objects.create(customer=customer)
        so_line = SalesOrderLine.objects.create(sales_order=so, product=cp, quantity=8)

        client.force_login(user)
        resp = client.post(
            reverse("sales:sales-order-ship", args=[so.pk]),
            {"ship_all": "1"},
        )
        assert resp.status_code == 302

        so_line.refresh_from_db()
        assert so_line.complete is True
        assert so_line.quantity_shipped == 8

        inv_finished.refresh_from_db()
        assert inv_finished.quantity == 2  # 10 - 8

        # --- 5. Verify all ledgers ---
        # purchase ledger: 100 raw at $2 each
        pl = PurchaseLedger.objects.get(product=raw_material)
        assert pl.value == 200

        # sales ledger: 8 finished at $50 each
        sl = SalesLedger.objects.get(product=finished_product)
        assert sl.value == 400
        assert sl.customer == customer

        # inventory ledger has full audit trail
        raw_ledger = InventoryLedger.objects.filter(product=raw_material).order_by("pk")
        assert raw_ledger.count() == 2  # +100 purchase, -50 production
        assert raw_ledger[0].quantity == 100
        assert raw_ledger[0].action == "Purchase Order"
        assert raw_ledger[1].quantity == -50
        assert raw_ledger[1].action == "Production"

        finished_ledger = InventoryLedger.objects.filter(
            product=finished_product
        ).order_by("pk")
        assert finished_ledger.count() == 2  # +10 production, -8 sales
        assert finished_ledger[0].quantity == 10
        assert finished_ledger[0].action == "Production"
        assert finished_ledger[1].quantity == -8
        assert finished_ledger[1].action == "Sales Order"

    def test_inventory_never_goes_negative_in_cycle(self, client, user):
        """Selling more than available is rejected, even mid-cycle."""
        product = Product.objects.create(name="Scarce Item")
        supplier = Supplier.objects.create(name="Tiny Supplier")
        sp = SupplierProduct.objects.create(supplier=supplier, product=product, cost=5)
        po = PurchaseOrder.objects.create(supplier=supplier)
        po_line = PurchaseOrderLine.objects.create(
            purchase_order=po, product=sp, quantity=3
        )
        receive_purchase_order_line(po_line, 3)

        inv = Inventory.objects.get(product=product)
        assert inv.quantity == 3

        customer = Customer.objects.create(name="Demanding Customer")
        cp = CustomerProduct.objects.create(
            customer=customer, product=product, price=20
        )
        so = SalesOrder.objects.create(customer=customer)
        so_line = SalesOrderLine.objects.create(sales_order=so, product=cp, quantity=5)

        client.force_login(user)
        resp = client.post(
            reverse("sales:sales-order-ship", args=[so.pk]),
            {f"shipped_{so_line.pk}": "5"},
        )
        # should fail — only 3 in stock
        assert resp.status_code == 200
        assert b"Not enough inventory" in resp.content

        # inventory unchanged
        inv.refresh_from_db()
        assert inv.quantity == 3

        # ship what we actually have
        resp = client.post(
            reverse("sales:sales-order-ship", args=[so.pk]),
            {f"shipped_{so_line.pk}": "3"},
        )
        assert resp.status_code == 302

        inv.refresh_from_db()
        assert inv.quantity == 0

        so_line.refresh_from_db()
        assert so_line.quantity_shipped == 3
        assert so_line.complete is False  # only 3 of 5

    def test_required_cache_reflects_procurement_and_sales(self):
        """required_cached should drop after procurement receive covers sales demand."""
        product = Product.objects.create(name="Tracked Item")
        inv = Inventory.objects.get(product=product)
        assert inv.quantity == 0

        # create a sales order demanding 20 units
        customer = Customer.objects.create(name="Cache Customer")
        cp = CustomerProduct.objects.create(
            customer=customer, product=product, price=10
        )
        so = SalesOrder.objects.create(customer=customer)
        SalesOrderLine.objects.create(sales_order=so, product=cp, quantity=20)

        # required should now show a shortage
        refresh_required_cache_for_products([product.pk])
        inv.refresh_from_db()
        assert inv.required_cached > 0

        # procure enough stock to cover the order
        supplier = Supplier.objects.create(name="Cache Supplier")
        sp = SupplierProduct.objects.create(supplier=supplier, product=product, cost=1)
        po = PurchaseOrder.objects.create(supplier=supplier)
        po_line = PurchaseOrderLine.objects.create(
            purchase_order=po, product=sp, quantity=25
        )
        receive_purchase_order_line(po_line, 25)
        refresh_required_cache_for_products([product.pk])

        inv.refresh_from_db()
        assert inv.quantity == 25
        assert inv.required_cached == 0  # 25 on hand, 20 needed, no shortage
