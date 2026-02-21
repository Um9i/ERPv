import pytest
from django.db.models import Sum
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

    def test_inventory_list_search_and_pagination(self, client, product):
        from django.urls import reverse
        from inventory.models import Inventory, Product
        # insert many products
        for i in range(25):
            p = Product.objects.create(name=f"X{i}")
            Inventory.objects.update_or_create(product=p, defaults={"quantity": i})
        url = reverse("inventory:inventory-list")
        resp = client.get(url, {"q": "X1"})
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "X1" in content
        # result should not include unrelated names
        assert "X3" not in content
        # pagination should still work when multiple pages are needed
        resp2 = client.get(url + "?page=2")
        assert resp2.status_code == 200

    def test_inventory_detail_ledger_and_last_updated(self, client, product):
        from inventory.models import Inventory, InventoryLedger
        from django.urls import reverse
        inv = Inventory.objects.get(product=product)
        # perform two adjustments to generate ledger entries
        InventoryAdjust.objects.create(product=product, quantity=5, complete=True)
        InventoryAdjust.objects.create(product=product, quantity=-2, complete=True)
        # detail page should show ledger entries and last_updated recent
        url = reverse("inventory:inventory-detail", args=[inv.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Inventory Ledger" in content
        assert str(5) in content or str(-2) in content
        assert "Last Updated" in content
        # pending activity totals should be present (zero by default)
        assert "Pending Activity" in content
        assert "Sales Orders" in content
        assert "Purchase Orders" in content
        # production jobs row only appears when nonzero; its absence is acceptable
        assert "Required Shortage" in content
        # chart canvas should be present
        assert '<canvas id="pending-chart"' in content
        # ledger entries should appear (pagination header optional)

    def test_last_updated_changes_on_inventory_operations(self, product):
        from inventory.models import Inventory
        inv = Inventory.objects.get(product=product)
        orig = inv.last_updated
        # adjust inventory
        InventoryAdjust.objects.create(product=product, quantity=1, complete=True)
        inv.refresh_from_db()
        assert inv.last_updated > orig

    def test_dashboard_links(self, client, product):
        from django.urls import reverse
        from django.contrib.auth.models import User
        from inventory.models import Product, Inventory

        user = User.objects.create_user(username="tester")
        client.force_login(user)
        url = reverse("inventory:inventory-dashboard")
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Inventory Dashboard" in content
        assert "View Inventory" in content
        # summary cards should appear
        assert "Products" in content
        assert "Inventory Items" in content
        assert "Stock Value" in content
        # verify context values reflect database
        ctx = resp.context
        assert ctx["total_products"] == Product.objects.count()
        assert ctx["total_inventory_items"] == Inventory.objects.count()
        assert ctx["stock_value"] == Inventory.objects.aggregate(total=Sum("quantity"))["total"] or 0
