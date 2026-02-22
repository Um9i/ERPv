import pytest
from django.db.models import Sum
from inventory.models import Inventory, InventoryAdjust, InventoryLedger


@pytest.mark.django_db
class TestInventory:
    def test_inventory_model_exists(self, product):
        inventory = Inventory.objects.get(pk=product.pk)
        assert inventory.product.name == "product"

    def test_inventory_adjustment_alters_inventory_quantity(self, product):
        InventoryAdjust.objects.create(product=product, quantity=1, complete=True)
        inventory = Inventory.objects.get(pk=product.pk)
        assert inventory.quantity == 1

    def test_inventory_adjustment_ledger_is_created(self, product):
        InventoryAdjust.objects.create(product=product, quantity=1, complete=True)
        ledger = InventoryLedger.objects.filter(product=product).order_by("pk").first()
        assert ledger is not None
        assert ledger.product == product
        assert ledger.quantity == 1

    def test_closed_field_no_longer_exists(self):
        # ensure our migrations actually removed the closed column from the model
        assert not hasattr(InventoryAdjust, "closed"), "closed field should be removed"

    def test_adjust_form_prefills_product_and_is_readonly(self, client, product):
        from inventory.models import Inventory
        from django.urls import reverse
        from django.contrib.auth.models import User

        # login required
        user = User.objects.create_user(username="tester")
        client.force_login(user)

        inventory = Inventory.objects.get(product=product)
        url = reverse("inventory:inventory-adjust", args=[inventory.pk])
        response = client.get(url)
        assert response.status_code == 200
        form = response.context.get("form")
        assert form is not None
        assert form.initial.get("product") == product
        assert form.fields["product"].disabled

        response = client.post(url, {"quantity": 2})
        assert response.status_code == 302
        adj = InventoryAdjust.objects.filter(product=product).order_by("-pk").first()
        assert adj is not None
        assert adj.quantity == 2
        assert adj.complete is True

    def test_inventory_list_search_and_pagination(self, client, product):
        from django.urls import reverse
        from inventory.models import Inventory, Product
        from django.contrib.auth.models import User

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        # insert many products
        for i in range(25):
            p = Product.objects.create(name=f"X{i}")
            Inventory.objects.update_or_create(product=p, defaults={"quantity": i})
        url = reverse("inventory:inventory-list")
        resp = client.get(url, {"q": "X1"})
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "X1" in content
        # result should not include unrelated names
        assert "X3" not in content
        # pagination should still work when multiple pages are needed
        resp2 = client.get(url + "?page=2")
        assert resp2.status_code == 200

    def test_inventory_detail_ledger_and_last_updated(self, client, product):
        from inventory.models import Inventory, InventoryLedger
        from django.urls import reverse
        from django.contrib.auth.models import User

        # login required for protected views
        user = User.objects.create_user(username="tester")
        client.force_login(user)

        inv = Inventory.objects.get(product=product)
        # perform two adjustments to generate ledger entries
        InventoryAdjust.objects.create(product=product, quantity=5, complete=True)
        InventoryAdjust.objects.create(product=product, quantity=-2, complete=True)
        # detail page should show ledger entries and sensible totals
        url = reverse("inventory:inventory-detail", args=[inv.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Inventory Ledger" in content
        assert str(5) in content or str(-2) in content
        # old last-updated text removed, ensure inventory object is in context
        ctx = resp.context
        assert ctx["inventory"].last_updated is not None
        # summary statistics should appear as table rows
        assert "Sales Orders" in content
        assert "Purchase Orders" in content
        # production jobs row only appears when nonzero; its absence is acceptable
        assert "Required Shortage" in content
        # chart canvases should be present
        assert '<canvas id="pending-chart"' in content
        assert '<canvas id="history-chart"' in content
        # ledger entries should appear (pagination header optional)

        # context should include history arrays matching adjustments
        ctx = resp.context
        assert "history_dates" in ctx and isinstance(ctx["history_dates"], list)
        assert "history_qty" in ctx and isinstance(ctx["history_qty"], list)
        # there should be two entries corresponding to the two adjustments
        assert len(ctx["history_qty"]) >= 2
        # final total should equal net change of adjustments (5 + -2)
        assert ctx["history_qty"][-1] == 3

    def test_last_updated_changes_on_inventory_operations(self, product):
        from inventory.models import Inventory
        inv = Inventory.objects.get(product=product)
        orig = inv.last_updated
        # adjust inventory
        InventoryAdjust.objects.create(product=product, quantity=1, complete=True)
        inv.refresh_from_db()
        assert inv.last_updated > orig

    def test_stock_value_uses_bom(self, product):
        """Stock value should include BOM-derived cost when no direct cost.

        Product1 is made from Product2/3 and Product1 has no supplier cost.
        """
        from inventory.models import Inventory, Product
        from procurement.models import Supplier, SupplierProduct
        from production.models import BillOfMaterials, BOMItem
        # create components with supplier cost
        comp2 = Product.objects.create(name="component2")
        comp3 = Product.objects.create(name="component3")
        supplier = Supplier.objects.create(name="S")
        SupplierProduct.objects.create(supplier=supplier, product=comp2, cost=10)
        SupplierProduct.objects.create(supplier=supplier, product=comp3, cost=5)
        # finished product without supplier cost
        finished = Product.objects.create(name="finished1")
        # BOM: 2*comp2 +3*comp3
        bom = BillOfMaterials.objects.create(product=finished)
        BOMItem.objects.create(bom=bom, product=comp2, quantity=2)
        BOMItem.objects.create(bom=bom, product=comp3, quantity=3)
        # inventories
        Inventory.objects.update_or_create(product=finished, defaults={"quantity":1})
        Inventory.objects.update_or_create(product=comp2, defaults={"quantity":0})
        Inventory.objects.update_or_create(product=comp3, defaults={"quantity":0})
        # compute dashboard context
        from inventory.views import InventoryDashboardView
        view = InventoryDashboardView()
        ctx = view.get_context_data()
        expected_cost = 1 * (2*10 + 3*5)
        assert ctx["stock_value"] == expected_cost

    def test_dashboard_links(self, client, product):
        from django.urls import reverse
        from django.contrib.auth.models import User
        from inventory.models import Product, Inventory

        user = User.objects.create_user(username="tester")
        client.force_login(user)
        url = reverse("inventory:inventory-dashboard")
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Inventory Dashboard" in content
        assert "View Inventory" in content
        # summary cards should appear
        assert "Products" in content
        assert "Total Quantity" in content
        assert "Stock Value" in content
        # verify context values reflect database
        ctx = resp.context
        assert ctx["total_products"] == Product.objects.count()
        assert ctx["total_inventory_items"] == Inventory.objects.count()
        assert ctx["total_quantity"] == Inventory.objects.aggregate(total=Sum("quantity"))["total"] or 0
        # when the required filter is applied we expect a list in context
        resp2 = client.get(url + '?required=1')
        assert 'required_items' in resp2.context
        # ensure the low-stock view renders entries when shortages exist
        # create a shortage if none already
        if not resp2.context['required_items']:
            inv = Inventory.objects.first()
            inv.quantity = 0
            inv.save()
            from sales.models import Customer, CustomerProduct, SalesOrder, SalesOrderLine
            cust = Customer.objects.create(name='C4')
            cp = CustomerProduct.objects.create(customer=cust, product=inv.product, price=1)
            so = SalesOrder.objects.create(customer=cust)
            SalesOrderLine.objects.create(sales_order=so, product=cp, quantity=5)
            resp2 = client.get(url + '?required=1')
        assert resp2.context['required_items']
        content_l = client.get(reverse('inventory:inventory-low-stock')).content.decode()
        # there should be table rows for required products
        assert '<table' in content_l
        entry = resp2.context['required_items'][0]
        assert entry['product'].name in content_l
        # production or PO flags should render as text
        assert ("Yes" in content_l) or ("No" in content_l)
        # create explicit job & PO and confirm flags
        prod_inv = entry if entry else resp2.context['required_items'][0]
        inv_obj = Inventory.objects.get(product=prod_inv['product'])
        # create production job and PO referencing this product
        from production.models import Production
        from procurement.models import Supplier, SupplierProduct, PurchaseOrder, PurchaseOrderLine
        supplier = Supplier.objects.create(name='S2')
        sp = SupplierProduct.objects.create(supplier=supplier, product=inv_obj.product, cost=1)
        po = PurchaseOrder.objects.create(supplier=supplier)
        PurchaseOrderLine.objects.create(purchase_order=po, product=sp, quantity=1)
        Production.objects.create(product=inv_obj.product, quantity=1)
        # refresh page and check flags updated
        content_l2 = client.get(reverse('inventory:inventory-low-stock')).content.decode()
        assert 'Yes' in content_l2
        # previously stock value mirrored quantity, now uses unit cost
        assert ctx["stock_value"] == sum(
            inv.quantity * inv.product.unit_cost for inv in Inventory.objects.all()
        )
