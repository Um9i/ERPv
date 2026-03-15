"""Tests for procurement services and check_notifications command."""

from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone

from inventory.models import Inventory, InventoryLocation, Location, Product
from procurement.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierProduct,
)
from procurement.services import (
    best_supplier_products,
    pending_po_by_product,
    receive_purchase_order_line,
)

pytestmark = pytest.mark.integration


# ── best_supplier_products ───────────────────────────────────────────
class TestBestSupplierProducts:
    @pytest.fixture
    def two_suppliers(self, db):
        s1 = Supplier.objects.create(name="Cheap Co")
        s2 = Supplier.objects.create(name="Budget Co")
        return s1, s2

    @pytest.fixture
    def product(self, db):
        return Product.objects.create(name="Test Part")

    def test_picks_cheapest_supplier(self, two_suppliers, product):
        s1, s2 = two_suppliers
        SupplierProduct.objects.create(supplier=s1, product=product, cost=Decimal("5"))
        SupplierProduct.objects.create(supplier=s2, product=product, cost=Decimal("10"))
        best = best_supplier_products([product.pk])
        assert best[product.pk].supplier_id == s1.pk

    def test_tiebreak_by_supplier_total(self, two_suppliers, product):
        s1, s2 = two_suppliers
        # Same cost for our product
        SupplierProduct.objects.create(supplier=s1, product=product, cost=Decimal("5"))
        SupplierProduct.objects.create(supplier=s2, product=product, cost=Decimal("5"))
        # But s1 has higher aggregate cost overall (another product)
        other = Product.objects.create(name="Other Part")
        SupplierProduct.objects.create(supplier=s1, product=other, cost=Decimal("100"))
        SupplierProduct.objects.create(supplier=s2, product=other, cost=Decimal("1"))
        best = best_supplier_products([product.pk])
        # s2 has lower total, so wins the tiebreak
        assert best[product.pk].supplier_id == s2.pk


# ── pending_po_by_product ────────────────────────────────────────────
class TestPendingPO:
    def test_returns_pending_quantities(self, db):
        s = Supplier.objects.create(name="Sup")
        p = Product.objects.create(name="PO Part")
        sp = SupplierProduct.objects.create(supplier=s, product=p, cost=Decimal("1"))
        po = PurchaseOrder.objects.create(supplier=s)
        PurchaseOrderLine.objects.create(
            purchase_order=po, product=sp, quantity=10, quantity_received=3
        )
        result = pending_po_by_product([p.pk])
        assert result[p.pk] == 7


# ── receive_purchase_order_line ──────────────────────────────────────
class TestReceivePOLine:
    @pytest.fixture
    def po_setup(self, db):
        s = Supplier.objects.create(name="Receiver Sup")
        p = Product.objects.create(name="Recv Part")
        sp = SupplierProduct.objects.create(supplier=s, product=p, cost=Decimal("10"))
        po = PurchaseOrder.objects.create(supplier=s)
        line = PurchaseOrderLine.objects.create(
            purchase_order=po, product=sp, quantity=10
        )
        return line, p

    def test_receive_zero_returns_none(self, po_setup):
        line, _ = po_setup
        assert receive_purchase_order_line(line, 0) is None

    def test_partial_receive(self, po_setup):
        line, p = po_setup
        pid = receive_purchase_order_line(line, 3)
        assert pid == p.pk
        line.refresh_from_db()
        assert line.quantity_received == 3
        assert not line.complete

    def test_full_receive_completes_line(self, po_setup):
        line, p = po_setup
        receive_purchase_order_line(line, 10)
        line.refresh_from_db()
        assert line.complete is True
        assert line.closed is True

    def test_receive_routes_to_single_bin(self, po_setup):
        line, p = po_setup
        inv = Inventory.objects.get(product=p)
        loc = Location.objects.create(name="Dock-1")
        il = InventoryLocation.objects.create(inventory=inv, location=loc, quantity=0)
        receive_purchase_order_line(line, 5)
        il.refresh_from_db()
        assert il.quantity == 5


# ── check_notifications command ──────────────────────────────────────
class TestCheckNotificationsCommand:
    def test_no_active_users(self, db):
        out = StringIO()
        call_command("check_notifications", stdout=out)
        assert "No active users" in out.getvalue()

    def test_creates_low_stock_notifications(self, db):
        User.objects.create_user("notify_user", is_staff=True)
        p = Product.objects.create(name="Low Stock Item")
        Inventory.objects.filter(product=p).update(required_cached=10)
        out = StringIO()
        call_command("check_notifications", stdout=out)
        assert "notification" in out.getvalue().lower()

    def test_creates_overdue_po_notifications(self, db):
        User.objects.create_user("po_user", is_staff=True)
        s = Supplier.objects.create(name="Late Sup")
        po = PurchaseOrder.objects.create(
            supplier=s,
            due_date=timezone.now().date() - timezone.timedelta(days=5),
        )
        sp = SupplierProduct.objects.create(
            supplier=s,
            product=Product.objects.create(name="PO Prod"),
            cost=Decimal("1"),
        )
        PurchaseOrderLine.objects.create(purchase_order=po, product=sp, quantity=10)
        out = StringIO()
        call_command("check_notifications", stdout=out)
        assert "notification" in out.getvalue().lower()

    def test_email_summary_sent(self, db):
        User.objects.create_user("email_user", email="test@example.com", is_staff=True)
        p = Product.objects.create(name="Email Stock Item")
        Inventory.objects.filter(product=p).update(required_cached=5)

        from config.models import CompanyConfig

        CompanyConfig.objects.create(name="Test Co", email_notifications=True)

        out = StringIO()
        with patch("django.core.mail.send_mass_mail") as mock_mail:
            call_command("check_notifications", stdout=out)
            mock_mail.assert_called_once()
