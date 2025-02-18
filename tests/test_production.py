import pytest
from django.core.exceptions import ValidationError
from production.models import BillOfMaterials, BOMItem, Production
from inventory.models import Inventory, InventoryLedger


@pytest.mark.django_db
class TestBillOfMaterials:
    def test_bom_creation(self, product):
        bom = BillOfMaterials.objects.create(product=product)
        assert bom.product == product

    def test_bom_str(self, product):
        bom = BillOfMaterials.objects.create(product=product)
        assert str(bom) == product.name


@pytest.mark.django_db
class TestBOMItem:
    def test_bom_item_creation(self, product, bom):
        bom_item = BOMItem.objects.create(bom=bom, product=product, quantity=10)
        assert bom_item.bom == bom
        assert bom_item.product == product
        assert bom_item.quantity == 10

    def test_bom_item_str(self, product, bom):
        bom_item = BOMItem.objects.create(bom=bom, product=product, quantity=10)
        assert str(bom_item) == f"{product.name} x {bom_item.quantity}"

    def test_bom_item_clean(self, product, bom):
        bom_item = BOMItem(bom=bom, product=bom.product, quantity=10)
        with pytest.raises(ValidationError):
            bom_item.clean()

    def test_bom_item_clean_self_reference(self, product, bom):
        bom_item = BOMItem(bom=bom, product=product, quantity=10)
        bom_item.bom.product = product
        with pytest.raises(ValidationError):
            bom_item.clean()


@pytest.mark.django_db
class TestProduction:
    def test_production_creation(self, product):
        production = Production.objects.create(product=product, quantity=10)
        assert production.product == product
        assert production.quantity == 10
        assert production.complete == False
        assert production.closed == False
        assert production.bom_allocated == False
        assert production.bom_allocated_amount == None

    def test_production_str(self, product):
        production = Production.objects.create(product=product, quantity=10)
        assert str(production) == product.name

    def test_production_clean_no_bom(self, product):
        production = Production(product=product, quantity=10)
        with pytest.raises(ValidationError):
            production.clean()

    def test_production_clean_not_enough_inventory(self, product, bom, bom_item):
        production = Production(product=product, quantity=100, complete=True)
        with pytest.raises(ValidationError):
            production.clean()

    def test_production_save(self, product, bom, bom_item):
        production = Production.objects.create(product=product, quantity=10)
        production.save()
        assert production.bom_allocated == True
        assert production.bom_allocated_amount == 10

    def test_production_complete(self, product, bom, bom_item):
        production = Production.objects.create(product=product, quantity=10)
        production.save()
        production_complete = Production.objects.get(pk=1)
        production_complete.transaction_id = production_complete.pk
        production_complete.complete = True
        production_complete.save()
        inventory = Inventory.objects.get(product=product)
        assert inventory.quantity == 10
        ledger = InventoryLedger.objects.get(pk=1)
        assert ledger.quantity == -100
        assert ledger.action == "Production"
        assert ledger.transaction_id == production.pk
