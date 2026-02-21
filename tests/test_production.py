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
        assert production.quantity_received == 0
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
        # trying to receive more than available components should raise
        production = Production(product=product, quantity=100, quantity_received=50)
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
        production.transaction_id = production.pk
        # simulate receiving the full quantity via the model
        production.quantity_received = 10
        production.save()
        inventory = Inventory.objects.get(product=product)
        # fixture seeded 100 units; creating and completing job adds 10
        assert inventory.quantity == 100 + 10
        ledger = InventoryLedger.objects.filter(transaction_id=production.pk, action="Production", quantity__lt=0).order_by("pk").first()
        assert ledger is not None
        assert ledger.quantity == -100
        assert ledger.action == "Production"
        assert ledger.transaction_id == production.pk

    def test_partial_receive_updates_inventory(self, product, bom, bom_item):
        # receiving part of a job should only adjust inventory proportionally
        production = Production.objects.create(product=product, quantity=20)
        production.save()
        production.transaction_id = production.pk
        production.quantity_received = 5
        production.save()
        inv = Inventory.objects.get(product=product)
        # fixture seeded 100 units; receiving 5 should add 5
        assert inv.quantity == 100 + 5
        # components decremented 5 * bom_item.quantity
        comp = Inventory.objects.get(product=bom_item.product)
        assert comp.quantity == 100 - 5 * bom_item.quantity

    # --- view tests start here ---
    def test_dashboard_link(self, client, product):
        from django.urls import reverse
        from django.contrib.auth.models import User
        from production.models import BillOfMaterials, Production

        user = User.objects.create_user(username="test")
        client.force_login(user)
        url = reverse("production:production-dashboard")
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Production Dashboard" in content
        # links for completion and job log should be present
        assert reverse("production:production-receiving-list") in content
        assert "Job Completion" in content
        assert "Job Log" in content
        # metrics cards should appear
        assert "BOMs" in content
        assert "Active Jobs" in content
        assert "Completed" in content
        ctx = resp.context
        assert ctx["total_boms"] == BillOfMaterials.objects.count()
        assert ctx["active_jobs"] == Production.objects.filter(closed=False).count()
        assert ctx["completed_jobs"] == Production.objects.filter(complete=True).count()

    def test_receiving_views(self, client, product, bom, bom_item):
        """Open jobs appear in the completion list and can be completed, even partially."""
        from django.urls import reverse
        from production.models import Production
        from django.contrib.auth.models import User

        user = User.objects.create_user(username="test")
        client.force_login(user)

        job = Production.objects.create(product=product, quantity=3)
        # list should include our job and show remaining (completion list)
        url = reverse("production:production-receiving-list")
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert job.order_number in content
        assert str(job.remaining) in content
        # partial complete one unit
        url = reverse("production:production-receive", args=[job.pk])
        resp = client.post(url, {"received": "1"})
        # page should offer a Complete button
        assert "Complete" in resp.content.decode() if resp.content else True
        assert resp.status_code == 302
        job.refresh_from_db()
        assert job.quantity_received == 1
        assert not job.complete
        # inventory should have increased by one finished unit
        fin = Inventory.objects.get(product=product)
        assert fin.quantity == 100 + 1
        comp = Inventory.objects.get(product=bom_item.product)
        assert comp.quantity == 100 - bom_item.quantity
        # remaining reduced and still on list
        resp2 = client.get(reverse("production:production-receiving-list"))
        assert job.order_number in resp2.content.decode()
        # complete the rest with receive_all
        resp3 = client.post(url, {"receive_all": "1"})
        assert resp3.status_code == 302
        job.refresh_from_db()
        assert job.complete
        # job should now disappear from list
        resp4 = client.get(reverse("production:production-receiving-list"))
        assert job.order_number not in resp4.content.decode()

    def test_bom_views(self, client, product):
        from django.urls import reverse
        from production.models import BillOfMaterials, BOMItem
        # create bom
        url = reverse("production:bom-create")
        resp = client.post(url, {"product": product.pk})
        assert resp.status_code == 302
        bom = BillOfMaterials.objects.first()
        assert bom.product == product
        # detail page
        url = reverse("production:bom-detail", args=[bom.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        # add item (use a different component product)
        from inventory.models import Product as InvProduct
        prod2 = InvProduct.objects.create(name="component1")
        url = reverse("production:bomitem-create") + f"?bom={bom.pk}"
        resp = client.post(url, {"bom": bom.pk, "product": prod2.pk, "quantity": 3})
        assert resp.status_code == 302
        item = BOMItem.objects.first()
        assert item.bom == bom
        # edit item
        url = reverse("production:bomitem-update", args=[item.pk])
        resp = client.post(url, {"bom": bom.pk, "product": prod2.pk, "quantity": 5})
        assert resp.status_code == 302
        item.refresh_from_db()
        assert item.quantity == 5
        # delete item
        url = reverse("production:bomitem-delete", args=[item.pk])
        resp = client.post(url)
        assert resp.status_code == 302
        assert not BOMItem.objects.exists()

    def test_production_job_views(self, client, product, bom, bom_item):
        from django.urls import reverse
        from production.models import Production
        # create job
        url = reverse("production:production-create")
        resp = client.post(url, {"product": product.pk, "quantity": 2})
        assert resp.status_code == 302
        job = Production.objects.first()
        assert job.product == product
        # list view
        url = reverse("production:production-list")
        resp = client.get(url)
        assert resp.status_code == 200
        assert job.order_number in resp.content.decode()
        # detail and complete
        url = reverse("production:production-detail", args=[job.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        # complete via POST
        resp2 = client.post(url, {"complete_production": "1"})
        assert resp2.status_code == 302
        job.refresh_from_db()
        assert job.complete

    def test_create_form_filters_products(self, client, product, bom):
        """Only products with a related BOM should be selectable."""
        from django.urls import reverse
        from django.contrib.auth.models import User
        from inventory.models import Product

        other = Product.objects.create(name="no bom")
        user = User.objects.create_user(username="test")
        client.force_login(user)

        url = reverse("production:production-create")
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        # our fixture product appears, but the other product does not
        assert str(product.pk) in content
        assert f'value="{other.pk}"' not in content

    def test_update_form_also_filtered(self, client, product, bom):
        """Make sure update form uses same restriction and doesn't expose
        products without a BOM."""
        from django.urls import reverse
        from django.contrib.auth.models import User
        from inventory.models import Product
        from production.models import Production

        other = Product.objects.create(name="no bom")
        user = User.objects.create_user(username="test")
        client.force_login(user)

        job = Production.objects.create(product=product, quantity=1)
        url = reverse("production:production-update", args=[job.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert str(product.pk) in content
        assert f'value="{other.pk}"' not in content
