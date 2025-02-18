import pytest
from procurement.models import PurchaseLedger
from inventory.models import Inventory, InventoryLedger


@pytest.mark.django_db
class TestSupplier:
    def test_supplier_creation(self, supplier):
        assert supplier.name == "Test Supplier"

    def test_supplier_contact_creation(self, supplier_contact):
        assert supplier_contact.name == "Test Contact"

@pytest.mark.django_db
class TestSupplierProduct:
    def test_supplier_product_creation(self, supplier_product):
        assert supplier_product.cost == 10.00

    def test_on_purchase_order(self, supplier_product, purchase_order_line):
        assert supplier_product.on_purchase_order() == 5

@pytest.mark.django_db
class TestPurchaseOrder:
    def test_purchase_order_creation(self, purchase_order):
        assert purchase_order.supplier.name == "Test Supplier"

@pytest.mark.django_db
class TestPurchaseOrderLine:
    def test_purchase_order_line_creation(self, purchase_order_line):
        assert purchase_order_line.quantity == 5

    def test_purchase_order_line_save(self, purchase_order_line):
        inventory = Inventory.objects.get(pk=1)
        purchase_order_line.complete = True
        purchase_order_line.save()
        assert inventory.quantity == 0
        ledger = InventoryLedger.objects.get(pk=1)
        assert ledger.quantity == 5
        purchase_ledger = PurchaseLedger.objects.get(pk=1)
        assert purchase_ledger.quantity == 5