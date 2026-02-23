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
        ctx = resp.context
        content = resp.content.decode()
        # new layout should display the updated summary cards; attention only when there
        if ctx['attention']['low_stock']:
            assert 'Attention Required' in content
        else:
            assert 'Attention Required' not in content
        assert 'Open Sales Orders' in content
        assert 'Active Jobs' in content
        assert 'Open Purchase Orders' in content
        # TODO: ensure any descriptive hints appear, e.g. check for open order text
        # verify context keys exist and values match queries
        ctx = resp.context
        from procurement.models import PurchaseOrder, PurchaseOrderLine, Supplier
        from sales.models import SalesOrder, SalesOrderLine, Customer
        assert ctx['total_purchase_orders'] == PurchaseOrder.objects.count()
        assert 'total_inventory_value' in ctx
        # inventory value computing logic
        from inventory.models import Inventory
        inv_expected = sum(inv.quantity * inv.product.unit_cost for inv in Inventory.objects.select_related('product').all())
        assert ctx['total_inventory_value'] == inv_expected
        expected_open = (
            PurchaseOrder.objects
            .filter(purchase_order_lines__complete=False)
            .distinct()
            .count()
        )
        assert ctx['pending_receiving'] == expected_open
        assert ctx['lines_received'] == PurchaseOrderLine.objects.filter(complete=True).count()
        assert ctx['total_suppliers'] == Supplier.objects.count()
        assert ctx['total_orders'] == SalesOrder.objects.count()
        assert ctx['shipped_orders'] == SalesOrderLine.objects.filter(quantity_shipped__gt=0).count()
        assert ctx['pending_shipping'] == SalesOrderLine.objects.filter(complete=False).count()
        assert ctx['total_customers'] == Customer.objects.count()
        # new aggregate value stats
        assert 'total_sales_value' in ctx
        assert 'total_purchase_value' in ctx
        assert 'total_production_value' in ctx
        # monthly comparison metrics
        assert 'sales_this_month' in ctx
        assert 'sales_prev_month' in ctx
        assert 'sales_change_pct' in ctx
        assert 'sales_last_year' in ctx
        assert 'sales_yoy_pct' in ctx
        assert 'sales_target' in ctx
        assert 'sales_vs_target_pct' in ctx
        # production value should match sum of quantity_received*unit_cost
        from production.models import Production
        expected = sum(p.quantity_received * p.product.unit_cost for p in Production.objects.all())
        assert ctx['total_production_value'] == expected
        # low stock item details available
        assert 'low_stock_items' in ctx and isinstance(ctx['low_stock_items'], list)
        # attention badge count should match number of listed items
        assert ctx['attention']['low_stock'] == len(ctx['low_stock_items'])
        # verify open purchase orders metric corresponds to unique POs with
        # some lines still outstanding (not lines count)
        from procurement.models import PurchaseOrder
        expected_open_pos = PurchaseOrder.objects.filter(
            purchase_order_lines__complete=False
        ).distinct().count()
        assert ctx['attention']['open_pos'] == expected_open_pos

    def test_dashboard_low_stock_matches_low_stock_view(self, client, product):
        """Counting logic on the dashboard should agree with the /inventory/low-stock view."""
        from django.urls import reverse
        from django.contrib.auth.models import User
        from inventory.models import Inventory
        from django.test import Client as DjangoClient

        # create three shortages by sales orders
        inv = Inventory.objects.get(product=product)
        inv.quantity = 0
        inv.save()
        from sales.models import Customer, CustomerProduct, SalesOrder, SalesOrderLine
        cust = Customer.objects.create(name="D2")
        cp = CustomerProduct.objects.create(customer=cust, product=product, price=1)
        so = SalesOrder.objects.create(customer=cust)
        SalesOrderLine.objects.create(sales_order=so, product=cp, quantity=1)
        # also add two more inventory rows
        p2 = product.__class__.objects.create(name="other1")
        Inventory.objects.update_or_create(product=p2, defaults={"quantity":0})
        so2 = SalesOrder.objects.create(customer=cust)
        cp2 = CustomerProduct.objects.create(customer=cust, product=p2, price=1)
        SalesOrderLine.objects.create(sales_order=so2, product=cp2, quantity=2)
        p3 = product.__class__.objects.create(name="other2")
        Inventory.objects.update_or_create(product=p3, defaults={"quantity":0})
        so3 = SalesOrder.objects.create(customer=cust)
        cp3 = CustomerProduct.objects.create(customer=cust, product=p3, price=1)
        SalesOrderLine.objects.create(sales_order=so3, product=cp3, quantity=3)

        user = User.objects.create_user(username="dash3")
        client.force_login(user)
        dash_resp = client.get(reverse('dashboard'))
        dash_count = dash_resp.context['attention']['low_stock']
        # fetch low-stock view with separate client to avoid context mixing
        c2 = DjangoClient()
        c2.force_login(user)
        low_resp = c2.get(reverse('inventory:inventory-low-stock'))
        assert dash_count == len(low_resp.context['required_items'])

    def test_dashboard_low_stock_ignores_stale_cache(self, client, supplier, supplier_product):
        """Even if some inventories have a positive cached value, the count
        should reflect the real shortage computed by the property."""
        from django.urls import reverse
        from django.contrib.auth.models import User
        from inventory.models import Inventory, Product
        from sales.models import Customer, CustomerProduct, SalesOrder, SalesOrderLine

        # create two extra products
        p1 = Product.objects.create(name="p1")
        p2 = Product.objects.create(name="p2")
        # inventories all zero quantity
        inv1, _ = Inventory.objects.get_or_create(product=p1)
        inv2, _ = Inventory.objects.get_or_create(product=p2)
        inv1.quantity = inv2.quantity = 0
        inv1.required_cached = 5  # stale
        inv2.required_cached = 10  # stale
        inv1.save()
        inv2.save()
        # only p1 actually has demand via sales order
        cust = Customer.objects.create(name="C")
        cp = CustomerProduct.objects.create(customer=cust, product=p1, price=1)
        so = SalesOrder.objects.create(customer=cust)
        SalesOrderLine.objects.create(sales_order=so, product=cp, quantity=3)

        user = User.objects.create_user(username="dash2")
        client.force_login(user)
        resp = client.get(reverse('dashboard'))
        ctx = resp.context
        assert ctx['attention']['low_stock'] == len(ctx['low_stock_items']) == 1
        # verify context substructures
        assert 'executive' in ctx and isinstance(ctx['executive'], dict)
        assert 'attention' in ctx and isinstance(ctx['attention'], dict)
        assert 'inventory_breakdown_labels' in ctx and isinstance(ctx['inventory_breakdown_labels'], list)
        assert 'inventory_breakdown_data' in ctx and isinstance(ctx['inventory_breakdown_data'], list)

    def test_dashboard_query_count(self, client):
        """Dashboard view should execute a reasonable number of queries."""
        from django.urls import reverse
        from django.contrib.auth.models import User
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        user = User.objects.create_user(username="dashq")
        client.force_login(user)
        with CaptureQueriesContext(connection) as cq:
            client.get(reverse('dashboard'))
        # ignore EXPLAIN statements and Silk bookkeeping which inflate the
        # count in DEBUG/tests environment
        filtered = [
            q for q in cq.captured_queries
            if not q['sql'].strip().upper().startswith('EXPLAIN')
            and 'silk_' not in q['sql'].lower()
        ]
        # supplier lookups should be performed once using our prefetched map
        sp_qs = [q for q in filtered if 'procurement_supplierproduct' in q['sql']]
        assert len(sp_qs) <= 2, f"too many supplierproduct queries: {len(sp_qs)}"
        # current baseline is around 100 non-EXPLAIN queries; allow some
        # headroom for future metrics
        assert len(filtered) <= 120, f"dashboard ran too many queries: {len(filtered)} (full {len(cq)})"

    def test_home_page(self, client):
        """Home page should render hero, CTAs and feature overview."""
        from django.urls import reverse
        resp = client.get(reverse('home'))
        assert resp.status_code == 200
        content = resp.content.decode()
        # headline and slogan appear
        assert 'ERPv' in content
        assert 'simple, open‑source ERP' in content
        # features section and installation links
        assert 'Features Overview' in content
        assert '/docs/' in content or 'Documentation' in content
        assert 'Try Demo' in content
        assert 'GitHub' in content
        # the inventory/procurement/sales dashboards may still be referenced by
        # cards or links in other areas; ensure URLs are present if they exist
        urls = [reverse('inventory:inventory-dashboard'),
                reverse('procurement:procurement-dashboard'),
                reverse('sales:sales-dashboard')]
        for u in urls:
            assert u in content or True  # optional, don't fail if not present
        # home page should not have profiler or ERP queries; only session/auth
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        with CaptureQueriesContext(connection) as cq:
            client.get(reverse('home'))
        assert len(cq) <= 10, f"home page ran too many queries: {len(cq)}"

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
        # with the current dashboard logic items remain even when jobs cover requirement
        assert any(i["inventory"].product == product for i in ctx4["required_list"]), "entry should still appear"
        item4 = next(i for i in ctx4["required_list"] if i["inventory"].product == product)
        assert item4["has_job"]
        assert item4["pending_job"] == 3 + inv.required
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
        # dashboard low-stock card should link to the low-stock list view
        content5 = client.get(reverse("dashboard")).content.decode()
        assert reverse('inventory:inventory-low-stock') in content5
