import pytest
from inventory.models import Inventory, InventoryAdjust, InventoryLedger


@pytest.mark.django_db
class TestInventory:
    def test_inventory_model_exists(self, product):
        inventory = Inventory.objects.get(pk=product.pk)
        assert inventory.product.name == "product"

    def test_inventory_adjustment_alters_inventory_quantity(self, product):
        InventoryAdjust.objects.create(product=product, quantity=1, complete=True)
        inventory = Inventory.objects.get(pk=product.pk)
        assert inventory.quantity == 1

    def test_inventory_adjustment_ledger_is_created(self, product):
        InventoryAdjust.objects.create(product=product, quantity=1, complete=True)
        ledger = InventoryLedger.objects.filter(product=product).order_by("pk").first()
        assert ledger is not None
        assert ledger.product == product
        assert ledger.quantity == 1

    def test_closed_field_no_longer_exists(self):
        # ensure our migrations actually removed the closed column from the model
        assert not hasattr(InventoryAdjust, "closed"), "closed field should be removed"

    def test_adjust_form_prefills_product_and_is_readonly(self, client, product):
        from inventory.models import Inventory
        from django.urls import reverse

        inventory = Inventory.objects.get(product=product)
        url = reverse("inventory:inventory-adjust", args=[inventory.pk])
        response = client.get(url)
        assert response.status_code == 200
        form = response.context.get("form")
        assert form is not None
        assert form.initial.get("product") == product
        assert form.fields["product"].disabled

        response = client.post(url, {"quantity": 2})
        assert response.status_code == 302
        adj = InventoryAdjust.objects.filter(product=product).order_by("-pk").first()
        assert adj is not None
        assert adj.quantity == 2
        assert adj.complete is True
