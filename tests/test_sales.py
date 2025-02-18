import pytest
from django.core.exceptions import ValidationError
from sales.models import SalesLedger
from inventory.models import Inventory, InventoryLedger


@pytest.mark.django_db
class TestCustomer:
    def test_customer_creation(self, customer):
        assert customer.name == "Test Customer"

    def test_customer_contact_creation(self, customer_contact):
        assert customer_contact.name == "Test Contact"

@pytest.mark.django_db
class TestCustomerProduct:
    def test_customer_product_creation(self, customer_product):
        assert customer_product.price == 10.00

    def test_on_sales_order(self, customer_product, sales_order_line):
        assert customer_product.on_sales_order() == 5

@pytest.mark.django_db
class TestSalesOrder:
    def test_sales_order_creation(self, sales_order):
        assert sales_order.customer.name == "Test Customer"

@pytest.mark.django_db
class TestSalesOrderLine:
    def test_sales_order_line_creation(self, sales_order_line):
        assert sales_order_line.quantity == 5


    def test_sales_order_line_save(self, sales_order_line_complete):
        inventory = Inventory.objects.get(product=sales_order_line_complete.product.product)
        assert inventory.quantity == 0
        ledger = InventoryLedger.objects.get(pk=1)
        assert ledger.quantity == -5
        sales_ledger = SalesLedger.objects.get(product=sales_order_line_complete.product.product)
        assert sales_ledger.quantity == 5

