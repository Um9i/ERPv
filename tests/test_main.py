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
        assert 'Total Purchase Orders' in content
        assert 'Pending Receiving' in content
        assert 'Lines Received' in content
        assert 'Total Suppliers' in content
        assert 'Total Orders' in content
        assert 'Shipped Orders' in content
        assert 'Pending Shipping' in content
        assert 'Total Customers' in content
        assert 'Open Sales Orders' in content
        assert 'Open Purchase Orders' in content
        assert 'Open Production Jobs' in content
        # verify additional headers
        assert 'Inventory' in content
        assert 'Procurement' in content
        assert 'Sales' in content
        assert 'Production' in content
        # verify context keys exist and values match queries
        ctx = resp.context
        from procurement.models import PurchaseOrder, PurchaseOrderLine, Supplier
        from sales.models import SalesOrder, SalesOrderLine, Customer
        assert ctx['total_purchase_orders'] == PurchaseOrder.objects.count()
        assert ctx['pending_receiving'] == PurchaseOrderLine.objects.filter(complete=False).count()
        assert ctx['lines_received'] == PurchaseOrderLine.objects.filter(complete=True).count()
        assert ctx['total_suppliers'] == Supplier.objects.count()
        assert ctx['total_orders'] == SalesOrder.objects.count()
        assert ctx['shipped_orders'] == SalesOrderLine.objects.filter(quantity_shipped__gt=0).count()
        assert ctx['pending_shipping'] == SalesOrderLine.objects.filter(complete=False).count()
        assert ctx['total_customers'] == Customer.objects.count()
        # verify stylesheet link and sidebar class are present
        assert '<link rel="stylesheet" href="' in content
        assert 'sidemenu' in content
        # ensure card titles are hyperlinked where applicable
        assert 'href="' in content  # at least one link
        from django.urls import reverse
        # check generated URLs appear in the HTML
        assert reverse('procurement:purchase-order-receiving-list') in content
        assert reverse('sales:sales-order-ship-list') in content

    def test_home_page(self, client):
        """Home page should render hero and feature cards."""
        from django.urls import reverse
        resp = client.get(reverse('home'))
        assert resp.status_code == 200
        content = resp.content.decode()
        assert 'Welcome to ERPv' in content
        # feature cards should reference app dashboards
        assert reverse('inventory:inventory-dashboard') in content
        assert reverse('procurement:procurement-dashboard') in content
        assert reverse('sales:sales-dashboard') in content

    def test_views_require_login(self, client):
        """Unauthenticated users are redirected from app views."""
        from django.urls import reverse
        # try several protected endpoints
        for url in [
            reverse('dashboard'),
            reverse('inventory:inventory-dashboard'),
            reverse('procurement:procurement-dashboard'),
            reverse('sales:sales-dashboard'),
            reverse('production:production-dashboard'),
        ]:
            resp = client.get(url)
            assert resp.status_code in (302, 301)
            assert reverse('login') in resp.url

    def test_registration_pages(self, client):
        """Registration form and completion pages render correctly."""
        from django.urls import reverse
        resp = client.get(reverse('django_registration_register'))
        assert resp.status_code == 200
        assert 'Create Account' in resp.content.decode()
        resp2 = client.post(reverse('django_registration_register'), {
            'username': 'newuser',
            'password1': 'complexpass123',
            'password2': 'complexpass123',
            'email': 'new@example.com'
        })
        assert resp2.status_code in (302, 301)
        completion = client.get(reverse('django_registration_complete'))
        assert 'Registration Complete' in completion.content.decode()

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
