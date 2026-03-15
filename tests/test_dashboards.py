"""Tests for dashboard schedule views."""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from inventory.models import Product
from procurement.models import PurchaseOrder, Supplier, SupplierProduct
from production.models import BillOfMaterials, BOMItem, Production
from sales.models import Customer, CustomerProduct, SalesOrder, SalesOrderLine

pytestmark = pytest.mark.integration


@pytest.fixture
def staff(db):
    return User.objects.create_user("dashuser", is_staff=True)


@pytest.fixture
def _shipping_data(db):
    """Create a sales order due today with an open line."""
    customer = Customer.objects.create(name="Dash Customer")
    product = Product.objects.create(name="Dash Prod", sale_price=10)
    cp = CustomerProduct.objects.create(customer=customer, product=product, price=10)
    so = SalesOrder.objects.create(customer=customer, ship_by_date=date.today())
    SalesOrderLine.objects.create(
        sales_order=so, product=cp, quantity=5, quantity_shipped=0
    )
    return so


@pytest.fixture
def _delivery_data(db):
    """Create a purchase order due today with an open line."""
    supplier = Supplier.objects.create(name="Dash Supplier")
    product = Product.objects.create(name="Dash Recv Prod")
    sp = SupplierProduct.objects.create(supplier=supplier, product=product, cost=5)
    po = PurchaseOrder.objects.create(supplier=supplier, due_date=date.today())
    from procurement.models import PurchaseOrderLine

    PurchaseOrderLine.objects.create(
        purchase_order=po, product=sp, quantity=10, quantity_received=0
    )
    return po


@pytest.fixture
def _production_data(db):
    """Create a production job due today."""
    product = Product.objects.create(name="Dash Prod Item")
    comp = Product.objects.create(name="Dash Comp")
    sup = Supplier.objects.create(name="Prod Supplier")
    SupplierProduct.objects.create(supplier=sup, product=comp, cost=1)
    bom = BillOfMaterials.objects.create(product=product)
    BOMItem.objects.create(bom=bom, product=comp, quantity=2)
    job = Production.objects.create(product=product, quantity=5, due_date=date.today())
    return job


class TestDashboardHome:
    def test_home_loads(self, client, staff):
        client.force_login(staff)
        resp = client.get(reverse("dashboards:dashboard-home"))
        assert resp.status_code == 200


class TestShippingSchedule:
    def test_loads_empty(self, client, staff):
        client.force_login(staff)
        resp = client.get(reverse("dashboards:shipping-schedule"))
        assert resp.status_code == 200

    def test_loads_with_data(self, client, staff, _shipping_data):
        client.force_login(staff)
        resp = client.get(reverse("dashboards:shipping-schedule"))
        assert resp.status_code == 200
        assert "Dash Customer" in resp.content.decode()

    def test_date_navigation(self, client, staff, _shipping_data):
        client.force_login(staff)
        tomorrow = date.today() + timedelta(days=1)
        resp = client.get(
            reverse("dashboards:shipping-schedule") + f"?date={tomorrow.isoformat()}"
        )
        assert resp.status_code == 200

    def test_invalid_date_fallback(self, client, staff):
        client.force_login(staff)
        resp = client.get(reverse("dashboards:shipping-schedule") + "?date=not-a-date")
        assert resp.status_code == 200

    def test_htmx_partial(self, client, staff, _shipping_data):
        client.force_login(staff)
        resp = client.get(
            reverse("dashboards:shipping-schedule"),
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200


class TestDeliverySchedule:
    def test_loads_empty(self, client, staff):
        client.force_login(staff)
        resp = client.get(reverse("dashboards:delivery-schedule"))
        assert resp.status_code == 200

    def test_loads_with_data(self, client, staff, _delivery_data):
        client.force_login(staff)
        resp = client.get(reverse("dashboards:delivery-schedule"))
        assert resp.status_code == 200
        assert "Dash Supplier" in resp.content.decode()

    def test_invalid_date_fallback(self, client, staff):
        client.force_login(staff)
        resp = client.get(reverse("dashboards:delivery-schedule") + "?date=bad")
        assert resp.status_code == 200

    def test_htmx_partial(self, client, staff, _delivery_data):
        client.force_login(staff)
        resp = client.get(
            reverse("dashboards:delivery-schedule"),
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200


class TestProductionSchedule:
    def test_loads_empty(self, client, staff):
        client.force_login(staff)
        resp = client.get(reverse("dashboards:production-schedule"))
        assert resp.status_code == 200

    def test_loads_with_data(self, client, staff, _production_data):
        client.force_login(staff)
        resp = client.get(reverse("dashboards:production-schedule"))
        assert resp.status_code == 200

    def test_invalid_date_fallback(self, client, staff):
        client.force_login(staff)
        resp = client.get(reverse("dashboards:production-schedule") + "?date=xyz")
        assert resp.status_code == 200

    def test_htmx_partial(self, client, staff, _production_data):
        client.force_login(staff)
        resp = client.get(
            reverse("dashboards:production-schedule"),
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200
