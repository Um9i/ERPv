import pytest

@pytest.mark.django_db
class TestMainDashboard:
    def test_dashboard_contains_statistics(self, client):
        from django.urls import reverse
        from django.contrib.auth.models import User
        user = User.objects.create_user(username="dashuser")
        client.force_login(user)
        url = reverse("dashboard")
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        # stats table should include the new counts (note label changed)
        assert 'Total Products' in content
        assert 'Products' in content
        assert 'Open Sales Orders' in content
        assert 'Open Purchase Orders' in content
        assert 'Open Production Jobs' in content
        # "Products we Produce" label was removed in redesign
        # verify stylesheet link and sidebar class are present
        assert '<link rel="stylesheet" href="' in content
        assert 'sidemenu' in content

    def test_required_list_excludes_with_open_job(self, client, product):
        """If a product already has an open production job, it does not show."""
        from django.urls import reverse
        from django.contrib.auth.models import User
        from inventory.models import Inventory
        from production.models import Production
        from sales.models import CustomerProduct, SalesOrder, SalesOrderLine, Customer

        # ensure only this product is in inventory for predictable ordering
        Inventory.objects.exclude(product=product).delete()
        # make inventory shortage by creating a sales order line
        inv = Inventory.objects.get(product=product)
        # ensure some stock is available far less than demand
        inv.quantity = 0
        inv.save()
        cust = Customer.objects.create(name="C")
        cust_prod = CustomerProduct.objects.create(customer=cust, product=product, price=1)
        so = SalesOrder.objects.create(customer=cust)
        SalesOrderLine.objects.create(sales_order=so, product=cust_prod, quantity=5)
        # now product has required>0
        assert inv.required > 0
        # first fetch dashboard to confirm it appears
        user = User.objects.create_user(username="dash2")
        client.force_login(user)
        resp = client.get(reverse("dashboard"))
        # product should appear in required_list initially
        ctx1 = resp.context
        assert any(item["inventory"].product == product for item in ctx1["required_list"])
        # now create open production job for that product, quantity less than requirement
        Production.objects.create(product=product, quantity=3)
        resp2 = client.get(reverse("dashboard"))
        ctx2 = resp2.context
        item2 = next((i for i in ctx2["required_list"] if i["inventory"].product == product), None)
        assert item2 is not None
        assert item2["has_job"]
        assert item2["pending_job"] == 3
        # now create a job that satisfies the requirement exactly
        Production.objects.create(product=product, quantity=inv.required)
        resp4 = client.get(reverse("dashboard"))
        ctx4 = resp4.context
        assert not any(i["inventory"].product == product for i in ctx4["required_list"])
        # after removing job, show again once we place a purchase order less than requirement
        Production.objects.filter(product=product).delete()
        from procurement.models import Supplier, SupplierProduct, PurchaseOrder, PurchaseOrderLine
        po_order = Supplier.objects.create(name="S2")
        sp2 = SupplierProduct.objects.create(supplier=po_order, product=product, cost=1)
        po2 = PurchaseOrder.objects.create(supplier=po_order)
        PurchaseOrderLine.objects.create(purchase_order=po2, product=sp2, quantity=2)
        resp5 = client.get(reverse("dashboard"))
        ctx5 = resp5.context
        item5 = next((i for i in ctx5["required_list"] if i["inventory"].product == product), None)
        assert item5 is not None
        assert item5["pending_po"] == 2
