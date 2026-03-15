"""Tests for sales model properties, computed fields, and validation."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from inventory.models import Inventory, InventoryLocation, Location, Product
from sales.models import (
    Customer,
    CustomerProduct,
    PickList,
    SalesLedger,
    SalesOrder,
    SalesOrderLine,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def customer(db):
    return Customer.objects.create(name="Test Cust")


@pytest.fixture
def product(db):
    return Product.objects.create(name="Widget", sale_price=Decimal("10.00"))


@pytest.fixture
def customer_product(customer, product):
    return CustomerProduct.objects.create(
        customer=customer, product=product, price=Decimal("25.00")
    )


@pytest.fixture
def sales_order(customer):
    return SalesOrder.objects.create(customer=customer)


@pytest.fixture
def stocked_product(product):
    """Ensure product has inventory so order lines can be completed."""
    Inventory.objects.filter(product=product).update(quantity=500)
    return product


# ── CustomerProduct ──────────────────────────────────────────────────
class TestCustomerProduct:
    def test_clean_negative_price_rejected(self, customer, product):
        cp = CustomerProduct(customer=customer, product=product, price=Decimal("-1"))
        with pytest.raises(ValidationError, match="negative"):
            cp.clean()

    def test_on_sales_order_no_orders(self, customer_product):
        assert customer_product.on_sales_order() == 0

    def test_on_sales_order_with_open_lines(self, customer_product, stocked_product):
        so = SalesOrder.objects.create(customer=customer_product.customer)
        SalesOrderLine.objects.create(
            sales_order=so,
            product=customer_product,
            quantity=10,
            quantity_shipped=3,
        )
        assert customer_product.on_sales_order() == 7


# ── SalesOrder properties ────────────────────────────────────────────
class TestSalesOrderProperties:
    def test_order_number(self, sales_order):
        assert sales_order.order_number.startswith("SO")

    def test_date_returns_created_at(self, sales_order):
        assert sales_order.date == sales_order.created_at

    def test_status_open_and_closed(self, customer_product, stocked_product):
        so = SalesOrder.objects.create(customer=customer_product.customer)
        SalesOrderLine.objects.create(
            sales_order=so, product=customer_product, quantity=5
        )
        assert so.status == "Open"

        # complete the line
        line = so.sales_order_lines.first()
        line.quantity_shipped = line.quantity
        line.complete = True
        line.closed = True
        line.save(update_fields=["quantity_shipped", "complete", "closed"])
        assert so.status == "Closed"

    def test_status_uses_annotation_when_present(self, sales_order):
        sales_order._has_open_lines = False
        assert sales_order.status == "Closed"
        sales_order._has_open_lines = True
        assert sales_order.status == "Open"

    def test_total_amount(self, customer_product, stocked_product):
        so = SalesOrder.objects.create(customer=customer_product.customer)
        SalesOrderLine.objects.create(
            sales_order=so, product=customer_product, quantity=4
        )
        # 4 × 25.00 = 100.00
        assert so.total_amount == Decimal("100.00")

    def test_total_amount_empty_order(self, sales_order):
        assert sales_order.total_amount == Decimal("0.00")

    def test_remaining_total(self, customer_product, stocked_product):
        so = SalesOrder.objects.create(customer=customer_product.customer)
        SalesOrderLine.objects.create(
            sales_order=so,
            product=customer_product,
            quantity=10,
            quantity_shipped=4,
        )
        # remaining = 6, price=25 → 150.00
        assert so.remaining_total == Decimal("150.00")

    def test_remaining_total_with_annotation(self, sales_order):
        sales_order._remaining_total = Decimal("42.00")
        assert sales_order.remaining_total == Decimal("42.00")

    def test_remaining_total_annotation_none(self, sales_order):
        sales_order._remaining_total = None
        assert sales_order.remaining_total == Decimal("0.00")

    def test_update_cached_total(self, customer_product, stocked_product):
        so = SalesOrder.objects.create(customer=customer_product.customer)
        SalesOrderLine.objects.create(
            sales_order=so, product=customer_product, quantity=2
        )
        so.update_cached_total()
        so.refresh_from_db()
        assert so.total_amount_cached == Decimal("50.00")


# ── SalesLedger ──────────────────────────────────────────────────────
class TestSalesLedger:
    def test_str(self, customer, product, stocked_product):
        ledger = SalesLedger.objects.create(
            product=product,
            quantity=5,
            customer=customer,
            value=Decimal("50.00"),
            transaction_id=1,
        )
        assert str(product) in str(ledger)

    def test_clean_negative_value(self, customer, product):
        ledger = SalesLedger(
            product=product,
            quantity=1,
            customer=customer,
            value=Decimal("-10.00"),
            transaction_id=1,
        )
        with pytest.raises(ValidationError, match="Value"):
            ledger.clean()

    def test_clean_zero_quantity(self, customer, product):
        ledger = SalesLedger(
            product=product,
            quantity=0,
            customer=customer,
            value=Decimal("10.00"),
            transaction_id=1,
        )
        with pytest.raises(ValidationError, match="Quantity"):
            ledger.clean()


# ── SalesOrderLine properties ────────────────────────────────────────
class TestSalesOrderLineProperties:
    def test_unit_price(self, customer_product, stocked_product):
        so = SalesOrder.objects.create(customer=customer_product.customer)
        line = SalesOrderLine.objects.create(
            sales_order=so, product=customer_product, quantity=3
        )
        assert line.unit_price == Decimal("25.00")

    def test_total_price(self, customer_product, stocked_product):
        so = SalesOrder.objects.create(customer=customer_product.customer)
        line = SalesOrderLine.objects.create(
            sales_order=so, product=customer_product, quantity=3
        )
        assert line.total_price == Decimal("75.00")

    def test_total_price_with_value_set(self, customer_product, stocked_product):
        so = SalesOrder.objects.create(customer=customer_product.customer)
        line = SalesOrderLine.objects.create(
            sales_order=so,
            product=customer_product,
            quantity=3,
            value=Decimal("60.00"),
        )
        assert line.total_price == Decimal("60.00")

    def test_shipped_total(self, customer_product, stocked_product):
        so = SalesOrder.objects.create(customer=customer_product.customer)
        line = SalesOrderLine.objects.create(
            sales_order=so,
            product=customer_product,
            quantity=10,
            quantity_shipped=4,
        )
        assert line.shipped_total == Decimal("100.00")

    def test_remaining(self, customer_product, stocked_product):
        so = SalesOrder.objects.create(customer=customer_product.customer)
        line = SalesOrderLine.objects.create(
            sales_order=so,
            product=customer_product,
            quantity=10,
            quantity_shipped=7,
        )
        assert line.remaining == 3

    def test_remaining_total(self, customer_product, stocked_product):
        so = SalesOrder.objects.create(customer=customer_product.customer)
        line = SalesOrderLine.objects.create(
            sales_order=so,
            product=customer_product,
            quantity=10,
            quantity_shipped=7,
        )
        # remaining=3, price=25 → 75.00
        assert line.remaining_total == Decimal("75.00")

    def test_str(self, customer_product, stocked_product):
        so = SalesOrder.objects.create(customer=customer_product.customer)
        line = SalesOrderLine.objects.create(
            sales_order=so, product=customer_product, quantity=1
        )
        assert "Widget" in str(line)


# ── PickList ─────────────────────────────────────────────────────────
class TestPickList:
    @pytest.fixture
    def setup_order(self, customer_product, stocked_product):
        """Create an SO with an open line and inventory."""
        so = SalesOrder.objects.create(customer=customer_product.customer)
        SalesOrderLine.objects.create(
            sales_order=so, product=customer_product, quantity=5
        )
        return so

    def test_generate_and_str(self, setup_order):
        pl = PickList.generate_for_order(setup_order)
        assert "Pick List" in str(pl)
        assert pl.lines.count() > 0

    def test_all_confirmed(self, setup_order):
        pl = PickList.generate_for_order(setup_order)
        assert not pl.all_confirmed
        pl.lines.filter(is_shortage=False).update(confirmed=True)
        assert pl.all_confirmed

    def test_refresh_regenerates(self, setup_order):
        pl = PickList.generate_for_order(setup_order)
        first_count = pl.lines.count()
        pl.refresh()
        assert pl.lines.count() == first_count

    def test_shortage_line(self, customer_product, product):
        """When inventory is 0, a shortage line is created."""
        Inventory.objects.filter(product=product).update(quantity=0)
        so = SalesOrder.objects.create(customer=customer_product.customer)
        SalesOrderLine.objects.create(
            sales_order=so, product=customer_product, quantity=5
        )
        pl = PickList.generate_for_order(so)
        assert pl.lines.filter(is_shortage=True).exists()

    def test_pick_from_location(self, customer_product, product):
        """Stock at a bin location is picked before unallocated."""
        inv = Inventory.objects.get(product=product)
        loc = Location.objects.create(name="Bin-A")
        InventoryLocation.objects.create(inventory=inv, location=loc, quantity=100)
        so = SalesOrder.objects.create(customer=customer_product.customer)
        SalesOrderLine.objects.create(
            sales_order=so, product=customer_product, quantity=3
        )
        pl = PickList.generate_for_order(so)
        loc_lines = pl.lines.filter(location=loc)
        assert loc_lines.exists()

    def test_pick_list_line_str(self, setup_order):
        pl = PickList.generate_for_order(setup_order)
        line = pl.lines.first()
        s = str(line)
        assert "×" in s
