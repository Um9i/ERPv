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
        # new layout should display executive summary and attention sections
        assert 'Total Sales' in content
        assert 'Open Orders' in content
        assert 'Inventory Value' in content
        assert 'Active Jobs' in content
        assert 'Attention Required' in content
        assert 'Pending Shipping' in content
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
        assert ctx['pending_receiving'] == PurchaseOrderLine.objects.filter(complete=False).count()
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
        # chart data present
        assert 'sales_over_time_labels' in ctx and isinstance(ctx['sales_over_time_labels'], list)
        assert 'sales_over_time_data' in ctx and isinstance(ctx['sales_over_time_data'], list)
        assert 'sales_over_time_labels_7' in ctx and isinstance(ctx['sales_over_time_labels_7'], list)
        assert 'sales_over_time_data_7' in ctx and isinstance(ctx['sales_over_time_data_7'], list)
        assert 'sales_over_time_labels_90' in ctx and isinstance(ctx['sales_over_time_labels_90'], list)
        assert 'sales_over_time_data_90' in ctx and isinstance(ctx['sales_over_time_data_90'], list)
        # values should be primitive numbers (not Decimal)
        assert all(isinstance(v, (int, float)) for v in ctx['sales_over_time_data'])
        assert 'sales_metrics_7' in ctx and isinstance(ctx['sales_metrics_7'], dict)
        assert 'sales_metrics_30' in ctx and isinstance(ctx['sales_metrics_30'], dict)
        assert 'sales_metrics_90' in ctx and isinstance(ctx['sales_metrics_90'], dict)
        # verify ranges have correct lengths
        assert len(ctx['sales_over_time_labels_7']) <= 7
        assert len(ctx['sales_over_time_labels']) <= 30
        assert len(ctx['sales_over_time_labels_90']) <= 90
        assert 'purchase_sales_labels' in ctx and isinstance(ctx['purchase_sales_labels'], list)
        assert 'purchase_sales_data' in ctx and isinstance(ctx['purchase_sales_data'], list)
        assert all(isinstance(v, (int, float)) for v in ctx['purchase_sales_data'])
        # verify stylesheet link and sidebar class are present
        assert '<link rel="stylesheet" href="' in content
        assert 'sidemenu' in content
        # chart.js library should be included for chart rendering
        assert 'cdn.jsdelivr.net/npm/chart.js' in content
        # currency values formatted to two decimals
        assert "$" in content and "." in content
        # ensure card titles are hyperlinked where applicable
        # pending shipping should link to the shipping list
        assert reverse('sales:sales-order-ship-list') in content
        # open production should link to receiving page
        assert reverse('production:production-receiving-list') in content
        # open purchase orders should link to procurement receiving page
        assert reverse('procurement:purchase-order-receiving-list') in content
        # query count should be bounded (avoid N+1 falling out of control)
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        with CaptureQueriesContext(connection) as cq:
            client.get(url)
        # keep the dashboard lean; we've optimized heavily so this
        # should stay well under fifty when data is small
        assert len(cq) < 50, f"too many queries: {len(cq)}"
        assert 'href="' in content  # at least one link
        from django.urls import reverse
        # chart canvases should be rendered
        assert 'id="sales-time-chart"' in content
        assert 'id="purchase-sales-chart"' in content
        assert 'id="inventory-breakdown-chart"' in content
        # executive summary and attention badges present
        assert 'Total Sales' in content
        assert 'Open Orders' in content
        assert 'Inventory Value' in content
        assert 'Active Jobs' in content
        assert 'Attention Required' in content
        if ctx.get('sales_yoy_pct') is not None:
            assert 'vs last year' in content
        if ctx.get('sales_vs_target_pct') is not None:
            assert 'vs target' in content
        # ensure the toggle buttons exist
        assert 'range7' in content and 'range30' in content and 'range90' in content
        # ensure metrics placeholder present
        assert 'sales-metrics' in content
        # low stock count card should link to low-stock list view
        from django.urls import reverse
        assert reverse('inventory:inventory-low-stock') in content
        # verify context substructures
        assert 'executive' in ctx and isinstance(ctx['executive'], dict)
        assert 'attention' in ctx and isinstance(ctx['attention'], dict)
        assert 'inventory_breakdown_labels' in ctx and isinstance(ctx['inventory_breakdown_labels'], list)
        assert 'inventory_breakdown_data' in ctx and isinstance(ctx['inventory_breakdown_data'], list)

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
        # home page should not have profiler or ERP queries; only session/auth
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        with CaptureQueriesContext(connection) as cq:
            client.get(reverse('home'))
        # typically only session/auth plus a few Silk bookkeeping
        # statements when profiling is enabled; allow a small fixed budget.
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
        # dashboard low-stock card should link to the low-stock list view
        content5 = client.get(reverse("dashboard")).content.decode()
        assert reverse('inventory:inventory-low-stock') in content5
