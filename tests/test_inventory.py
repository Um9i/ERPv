import pytest
from inventory.models import Inventory, InventoryAdjust, InventoryLedger


@pytest.mark.django_db
class TestInventory:
    def test_inventory_model_exists(self, product):
        inventory = Inventory.objects.get(pk=product.pk)
        assert inventory.product.name == "product 1"

    def test_inventory_adjustment_alters_inventory_quantity(self, product):
        InventoryAdjust.objects.create(product=product, quantity=1, complete=True)
        inventory = Inventory.objects.get(pk=product.pk)
        assert inventory.quantity == 1

    def test_inventory_adjustment_ledger_is_created(self, product):
        InventoryAdjust.objects.create(product=product, quantity=1, complete=True)
        ledger = InventoryLedger.objects.get(pk=1)
        assert ledger.product == product
        assert ledger.quantity == 1
