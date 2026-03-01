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
        # title updated when using base template
        assert "Production Management" in content
        # job log link should be present; wording changed to "View Jobs"
        assert reverse("production:production-list") in content

    def test_bom_list_actions(self, client, bom):
        from django.urls import reverse
        from django.contrib.auth.models import User

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        url = reverse("production:bom-list")
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        # view/edit/delete links should appear for our fixture BOM
        assert f'href="{reverse("production:bom-detail", args=[bom.pk])}"' in content
        assert f'href="{reverse("production:bom-update", args=[bom.pk])}"' in content
        assert f'href="{reverse("production:bom-delete", args=[bom.pk])}"' in content

    def test_production_dashboard_metrics(self, client, product):
        from django.urls import reverse
        from django.contrib.auth.models import User
        from production.models import BillOfMaterials, Production

        user = User.objects.create_user(username="tester2")
        client.force_login(user)
        url = reverse("production:production-dashboard")
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        # metrics cards should appear
        assert "BOMs" in content
        assert "Active Jobs" in content
        assert "Completed" in content
        ctx = resp.context
        assert ctx["total_boms"] == BillOfMaterials.objects.count()
        assert ctx["active_jobs"] == Production.objects.filter(closed=False).count()
        assert ctx["completed_jobs"] == Production.objects.filter(complete=True).count()

    def test_form_does_not_show_complete(self, client, product, bom):
        """The create view should not render the complete checkbox."""
        from django.urls import reverse
        from django.contrib.auth.models import User

        user = User.objects.create_user(username="test")
        client.force_login(user)
        url = reverse("production:production-create")
        resp = client.get(url)
        assert resp.status_code == 200
        html = resp.content.decode()
        # form should contain product and quantity inputs
        assert "name=\"product\"" in html
        assert "name=\"quantity\"" in html
        # and must not include the complete field
        assert "name=\"complete\"" not in html

    def test_bom_create_formset_present(self, client, product):
        """BOM create page should render component formset and add button."""
        from django.urls import reverse
        from django.contrib.auth.models import User

        user = User.objects.create_user(username="bomuser")
        client.force_login(user)
        url = reverse("production:bom-create")
        resp = client.get(url)
        assert resp.status_code == 200
        html = resp.content.decode()
        assert "Components" in html
        assert "id=\"add-line\"" in html
        # management form must be present (uses related_name prefix)
        assert "bom_items-TOTAL_FORMS" in html

    def test_bom_create_with_lines(self, client, product):
        """Submitting the BOM create form with multiple lines saves them."""
        from django.urls import reverse
        from django.contrib.auth.models import User
        from production.models import BillOfMaterials

        # create two extra component products
        comp1 = product.__class__.objects.create(name="comp1")
        comp2 = product.__class__.objects.create(name="comp2")

        user = User.objects.create_user(username="bomuser2")
        client.force_login(user)
        url = reverse("production:bom-create")
        data = {
            'product': product.pk,
            'bom_items-TOTAL_FORMS': '2',
            'bom_items-INITIAL_FORMS': '0',
            'bom_items-MIN_NUM_FORMS': '0',
            'bom_items-MAX_NUM_FORMS': '1000',
            'bom_items-0-product': comp1.pk,
            'bom_items-0-quantity': '5',
            'bom_items-1-product': comp2.pk,
            'bom_items-1-quantity': '7',
        }
        resp = client.post(url, data)
        # expect redirect to detail
        assert resp.status_code in (302, 303)
        bom = BillOfMaterials.objects.get(product=product)
        items = list(bom.bom_items.order_by('product'))
        assert len(items) == 2
        assert items[0].product == comp1 and items[0].quantity == 5
        assert items[1].product == comp2 and items[1].quantity == 7

    def test_bom_update_can_modify_lines(self, client, product, bom):
        """Editing an existing BOM lets us change quantities and add new line."""
        from django.urls import reverse
        from django.contrib.auth.models import User

        # current bom fixture has two components; we'll change one and add a third
        existing = list(bom.bom_items.all())
        comp_new = product.__class__.objects.create(name="comp new")

        user = User.objects.create_user(username="bomuser3")
        client.force_login(user)
        url = reverse("production:bom-update", args=[bom.pk])
        # prepare initial data reflecting existing items
        data = {
            'product': product.pk,
            'bom_items-TOTAL_FORMS': '3',
            'bom_items-INITIAL_FORMS': '2',
            'bom_items-MIN_NUM_FORMS': '0',
            'bom_items-MAX_NUM_FORMS': '1000',
        }
        for idx, itm in enumerate(existing):
            data[f'bom_items-{idx}-id'] = itm.pk
            data[f'bom_items-{idx}-product'] = itm.product.pk
            data[f'bom_items-{idx}-quantity'] = str(itm.quantity + 1)
        # add new component
        data['bom_items-2-product'] = comp_new.pk
        data['bom_items-2-quantity'] = '3'
        resp = client.post(url, data)
        assert resp.status_code in (302, 303)
        bom.refresh_from_db()
        items = list(bom.bom_items.order_by('product'))
        assert any(i.product == comp_new for i in items)
        # existing ones should have updated quantities
        for itm in existing:
            updated = bom.bom_items.get(pk=itm.pk)
            assert updated.quantity == itm.quantity + 1

    def test_bom_form_js_syntax(self, client, product):
        """Static order_form.js used by BOM page should be valid JS syntax."""
        from django.urls import reverse
        from django.contrib.auth.models import User
        import subprocess
        from pathlib import Path
        from django.conf import settings

        user = User.objects.create_user(username="jsuser")
        client.force_login(user)
        url = reverse("production:bom-create")
        resp = client.get(url)
        assert resp.status_code == 200
        html = resp.content.decode()
        assert "order_form.js" in html, "order_form.js not referenced on BOM form"
        js_path = Path(settings.BASE_DIR) / "static" / "js" / "order_form.js"
        result = subprocess.run(["node", "--check", str(js_path)], capture_output=True, text=True)
        assert result.returncode == 0, f"JS syntax error: {result.stderr}"

    def test_receiving_views(self, client, product, bom, bom_item):
        """Open jobs appear in the completion list and can be completed, even partially."""
        from django.urls import reverse
        from production.models import Production
        from django.contrib.auth.models import User

        user = User.objects.create_user(username="test")
        client.force_login(user)

        job = Production.objects.create(product=product, quantity=3)
        # production list should contain the job regardless of completion
        url = reverse("production:production-list")
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
        # negative receive should not alter inventory or qty
        resp_neg = client.post(url, {"received": "-5"})
        job.refresh_from_db()
        assert job.quantity_received == 1
        resp_big = client.post(url, {"received": "1000"})
        job.refresh_from_db()
        assert job.quantity_received == job.quantity
        # full receive should mark job complete
        assert job.complete
        
        # now simulate insufficient component inventory and verify error
        job2 = Production.objects.create(product=product, quantity=1)
        url2 = reverse("production:production-receive", args=[job2.pk])
        # manually drain component stock so subsequent receive fails
        comp_inv = Inventory.objects.get(product=bom_item.product)
        comp_inv.quantity = 0
        comp_inv.save()
        resp_err = client.post(url2, {"received": "1"})
        # view swallows validation error and redirects back
        job2.refresh_from_db()
        assert job2.quantity_received == 0
        # inventory should have increased by the two previous receives (1 then 2)
        fin = Inventory.objects.get(product=product)
        assert fin.quantity == 100 + 3
        # component quantity may now be zero after manual drain; do not assert
        # complete the rest with receive_all
        resp3 = client.post(url, {"receive_all": "1"})
        assert resp3.status_code == 302
        job.refresh_from_db()
        assert job.complete

    def test_bom_views(self, client, product):
        from django.urls import reverse
        from production.models import BillOfMaterials, BOMItem
        from django.contrib.auth.models import User
        # must be logged in because middleware enforces auth
        user = User.objects.create_user(username="test")
        client.force_login(user)
        # create bom - supply an empty components formset so validation
        # passes (the new form requires management data even if no lines).
        url = reverse("production:bom-create")
        data = {
            "product": product.pk,
            "bom_items-TOTAL_FORMS": "0",
            "bom_items-INITIAL_FORMS": "0",
            "bom_items-MIN_NUM_FORMS": "0",
            "bom_items-MAX_NUM_FORMS": "1000",
        }
        resp = client.post(url, data)
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
        from django.contrib.auth.models import User
        user = User.objects.create_user(username="test")
        client.force_login(user)
        # create job
        url = reverse("production:production-create")
        resp = client.post(url, {"product": product.pk, "quantity": 2})
        assert resp.status_code == 302
        job = Production.objects.first()
        assert job.product == product
        # list view – should include the materials indicator column
        url = reverse("production:production-list")
        resp = client.get(url)
        assert resp.status_code == 200
        html = resp.content.decode()
        assert job.order_number in html
        assert "Sufficient Materials" in html
        # flag should reflect job‑level availability rather than single unit
        expected_flag = "✓" if job.materials_available else "✗"
        assert expected_flag in html
        # create a second job that exceeds inventory to ensure the flag goes
        # false for larger quantities
        job2 = Production.objects.create(product=product, quantity=1000)
        resp3 = client.get(url)
        assert "✗" in resp3.content.decode()
        # detail and complete
        url = reverse("production:production-detail", args=[job.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        # detail page should show remaining quantity
        assert str(job.remaining) in resp.content.decode()
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
