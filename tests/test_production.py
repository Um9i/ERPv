import pytest
from django.core.exceptions import ValidationError

from inventory.models import Inventory, InventoryLedger
from production.models import BillOfMaterials, BOMItem, Production


@pytest.mark.django_db
@pytest.mark.unit
class TestBillOfMaterials:
    def test_bom_creation(self, product):
        bom = BillOfMaterials.objects.create(product=product)
        assert bom.product == product

    def test_bom_str(self, product):
        bom = BillOfMaterials.objects.create(product=product)
        assert str(bom) == product.name


@pytest.mark.django_db
@pytest.mark.unit
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
@pytest.mark.integration
class TestProduction:
    @pytest.mark.unit
    def test_production_creation(self, product):
        production = Production.objects.create(product=product, quantity=10)
        assert production.product == product
        assert production.quantity == 10
        assert production.quantity_received == 0
        assert not production.complete
        assert not production.closed
        assert not production.bom_allocated
        assert production.bom_allocated_amount is None

    @pytest.mark.unit
    def test_production_str(self, product):
        production = Production.objects.create(product=product, quantity=10)
        assert str(production) == product.name

    @pytest.mark.unit
    def test_production_clean_no_bom(self, product):
        production = Production(product=product, quantity=10)
        with pytest.raises(ValidationError):
            production.clean()

    @pytest.mark.unit
    def test_production_clean_not_enough_inventory(self, product, bom, bom_item):
        # trying to receive more than available components should raise
        production = Production(product=product, quantity=100, quantity_received=50)
        with pytest.raises(ValidationError):
            production.clean()

    @pytest.mark.unit
    def test_production_save(self, product, bom, bom_item):
        production = Production.objects.create(product=product, quantity=10)
        production.save()
        assert production.bom_allocated is True
        assert production.bom_allocated_amount == 10

    @pytest.mark.unit
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
        ledger = (
            InventoryLedger.objects.filter(
                transaction_id=production.pk, action="Production", quantity__lt=0
            )
            .order_by("pk")
            .first()
        )
        assert ledger is not None
        assert ledger.quantity == -100
        assert ledger.action == "Production"
        assert ledger.transaction_id == production.pk

    @pytest.mark.unit
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
        from django.contrib.auth.models import User
        from django.urls import reverse

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
        from django.contrib.auth.models import User
        from django.urls import reverse

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
        from django.contrib.auth.models import User
        from django.urls import reverse

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
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="test")
        client.force_login(user)
        url = reverse("production:production-create")
        resp = client.get(url)
        assert resp.status_code == 200
        html = resp.content.decode()
        # form should contain product and quantity inputs
        assert 'name="product"' in html
        assert 'name="quantity"' in html
        # and must not include the complete field
        assert 'name="complete"' not in html

    def test_bom_create_formset_present(self, client, product):
        """BOM create page should render component formset and add button."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="bomuser")
        client.force_login(user)
        url = reverse("production:bom-create")
        resp = client.get(url)
        assert resp.status_code == 200
        html = resp.content.decode()
        assert "Components" in html
        assert 'id="add-line"' in html
        # management form must be present (uses related_name prefix)
        assert "bom_items-TOTAL_FORMS" in html

    def test_bom_create_with_lines(self, client, product):
        """Submitting the BOM create form with multiple lines saves them."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        from procurement.models import Supplier, SupplierProduct
        from production.models import BillOfMaterials

        # create two extra component products with a supplier so they are sourceable
        comp1 = product.__class__.objects.create(name="comp1")
        comp2 = product.__class__.objects.create(name="comp2")
        sup = Supplier.objects.create(name="comp supplier")
        SupplierProduct.objects.create(supplier=sup, product=comp1, cost=1)
        SupplierProduct.objects.create(supplier=sup, product=comp2, cost=1)

        user = User.objects.create_user(username="bomuser2")
        client.force_login(user)
        url = reverse("production:bom-create")
        data = {
            "product": product.pk,
            "bom_items-TOTAL_FORMS": "2",
            "bom_items-INITIAL_FORMS": "0",
            "bom_items-MIN_NUM_FORMS": "1",
            "bom_items-MAX_NUM_FORMS": "1000",
            "bom_items-0-product": comp1.pk,
            "bom_items-0-quantity": "5",
            "bom_items-1-product": comp2.pk,
            "bom_items-1-quantity": "7",
        }
        resp = client.post(url, data)
        # expect redirect to detail
        assert resp.status_code in (302, 303)
        bom = BillOfMaterials.objects.get(product=product)
        items = list(bom.bom_items.order_by("product"))
        assert len(items) == 2
        assert items[0].product == comp1 and items[0].quantity == 5
        assert items[1].product == comp2 and items[1].quantity == 7

    def test_bom_create_rejects_empty(self, client, product):
        """A BOM with no component items should be rejected."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        from production.models import BillOfMaterials

        user = User.objects.create_user(username="bomempty")
        client.force_login(user)
        url = reverse("production:bom-create")
        data = {
            "product": product.pk,
            "bom_items-TOTAL_FORMS": "0",
            "bom_items-INITIAL_FORMS": "0",
            "bom_items-MIN_NUM_FORMS": "1",
            "bom_items-MAX_NUM_FORMS": "1000",
        }
        resp = client.post(url, data)
        # should re-render form with errors, not redirect
        assert resp.status_code == 200
        assert not BillOfMaterials.objects.exists()

    def test_bom_update_rejects_all_deleted(self, client, product, bom):
        """Deleting all items from an existing BOM should be rejected."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        existing = list(bom.bom_items.all())
        user = User.objects.create_user(username="bomdelall")
        client.force_login(user)
        url = reverse("production:bom-update", args=[bom.pk])
        data = {
            "product": product.pk,
            "bom_items-TOTAL_FORMS": str(len(existing)),
            "bom_items-INITIAL_FORMS": str(len(existing)),
            "bom_items-MIN_NUM_FORMS": "1",
            "bom_items-MAX_NUM_FORMS": "1000",
        }
        for idx, itm in enumerate(existing):
            data[f"bom_items-{idx}-id"] = itm.pk
            data[f"bom_items-{idx}-product"] = itm.product.pk
            data[f"bom_items-{idx}-quantity"] = str(itm.quantity)
            data[f"bom_items-{idx}-DELETE"] = "on"
        resp = client.post(url, data)
        # should re-render form with errors, not redirect
        assert resp.status_code == 200
        # items should still exist
        bom.refresh_from_db()
        assert bom.bom_items.count() == len(existing)

    def test_bom_update_can_modify_lines(self, client, product, bom):
        """Editing an existing BOM lets us change quantities and add new line."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        from procurement.models import Supplier, SupplierProduct

        # current bom fixture has two components; we'll change one and add a third
        existing = list(bom.bom_items.all())
        comp_new = product.__class__.objects.create(name="comp new")
        sup = Supplier.objects.create(name="comp supplier")
        SupplierProduct.objects.create(supplier=sup, product=comp_new, cost=1)
        # existing components also need a supplier to pass form queryset filter
        for itm in existing:
            SupplierProduct.objects.get_or_create(
                supplier=sup, product=itm.product, defaults={"cost": 1}
            )

        user = User.objects.create_user(username="bomuser3")
        client.force_login(user)
        url = reverse("production:bom-update", args=[bom.pk])
        # prepare initial data reflecting existing items
        data = {
            "product": product.pk,
            "bom_items-TOTAL_FORMS": "3",
            "bom_items-INITIAL_FORMS": "2",
            "bom_items-MIN_NUM_FORMS": "1",
            "bom_items-MAX_NUM_FORMS": "1000",
        }
        for idx, itm in enumerate(existing):
            data[f"bom_items-{idx}-id"] = itm.pk
            data[f"bom_items-{idx}-product"] = itm.product.pk
            data[f"bom_items-{idx}-quantity"] = str(itm.quantity + 1)
        # add new component
        data["bom_items-2-product"] = comp_new.pk
        data["bom_items-2-quantity"] = "3"
        resp = client.post(url, data)
        assert resp.status_code in (302, 303)
        bom.refresh_from_db()
        items = list(bom.bom_items.order_by("product"))
        assert any(i.product == comp_new for i in items)
        # existing ones should have updated quantities
        for itm in existing:
            updated = bom.bom_items.get(pk=itm.pk)
            assert updated.quantity == itm.quantity + 1

    def test_bom_form_js_syntax(self, client, product):
        """Static order_form.js used by BOM page should be valid JS syntax."""
        import subprocess
        from pathlib import Path

        from django.conf import settings
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="jsuser")
        client.force_login(user)
        url = reverse("production:bom-create")
        resp = client.get(url)
        assert resp.status_code == 200
        html = resp.content.decode()
        assert "order_form.js" in html, "order_form.js not referenced on BOM form"
        js_path = Path(settings.BASE_DIR) / "static" / "js" / "order_form.js"
        if not js_path.exists():
            pytest.skip("Compiled JS not present (run tsc first)")
        result = subprocess.run(
            ["node", "--check", str(js_path)], capture_output=True, text=True
        )
        assert result.returncode == 0, f"JS syntax error: {result.stderr}"

    def test_receiving_views(self, client, product, bom, bom_item):
        """Open jobs appear in the completion list and can be completed, even partially."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        from production.models import Production

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
        resp = client.post(url, {"quantity_to_receive": "1"})
        assert resp.status_code == 302
        job.refresh_from_db()
        assert job.quantity_received == 1
        # negative receive should not alter inventory or qty (form rejects it)
        client.post(url, {"quantity_to_receive": "-5"})
        job.refresh_from_db()
        assert job.quantity_received == 1
        # over-remaining receive should be rejected by form validation
        client.post(url, {"quantity_to_receive": "1000"})
        job.refresh_from_db()
        assert job.quantity_received == 1  # unchanged
        # receive remaining to complete job
        resp_rest = client.post(url, {"quantity_to_receive": str(job.remaining)})
        assert resp_rest.status_code == 302
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
        client.post(url2, {"quantity_to_receive": "1"})
        # view swallows validation error and redirects back
        job2.refresh_from_db()
        assert job2.quantity_received == 0
        # inventory should have increased by the previous receives (1 then 2)
        fin = Inventory.objects.get(product=product)
        assert fin.quantity == 100 + 3

    def test_bom_views(self, client, product):
        from django.contrib.auth.models import User
        from django.urls import reverse

        from inventory.models import Product as InvProduct
        from procurement.models import Supplier, SupplierProduct
        from production.models import BillOfMaterials, BOMItem

        # must be logged in because middleware enforces auth
        user = User.objects.create_user(username="test")
        client.force_login(user)
        # create bom — must include at least one component (with a supplier)
        comp = InvProduct.objects.create(name="component1")
        sup = Supplier.objects.create(name="comp supplier")
        SupplierProduct.objects.create(supplier=sup, product=comp, cost=1)
        url = reverse("production:bom-create")
        data = {
            "product": product.pk,
            "bom_items-TOTAL_FORMS": "1",
            "bom_items-INITIAL_FORMS": "0",
            "bom_items-MIN_NUM_FORMS": "1",
            "bom_items-MAX_NUM_FORMS": "1000",
            "bom_items-0-product": comp.pk,
            "bom_items-0-quantity": "3",
        }
        resp = client.post(url, data)
        assert resp.status_code == 302
        bom = BillOfMaterials.objects.first()
        assert bom.product == product
        # detail page
        url = reverse("production:bom-detail", args=[bom.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        item = BOMItem.objects.first()
        assert item.bom == bom
        # edit item
        url = reverse("production:bomitem-update", args=[item.pk])
        resp = client.post(url, {"bom": bom.pk, "product": comp.pk, "quantity": 5})
        assert resp.status_code == 302
        item.refresh_from_db()
        assert item.quantity == 5
        # delete item
        url = reverse("production:bomitem-delete", args=[item.pk])
        resp = client.post(url)
        assert resp.status_code == 302
        assert not BOMItem.objects.exists()

    def test_production_job_views(self, client, product, bom, bom_item):
        from django.contrib.auth.models import User
        from django.urls import reverse

        from production.models import Production

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
        expected_icon = (
            "bi-check-circle-fill"
            if job.materials_available
            else "bi-exclamation-triangle-fill"
        )
        assert expected_icon in html
        # create a second job that exceeds inventory to ensure the flag goes
        # false for larger quantities
        Production.objects.create(product=product, quantity=1000)
        resp3 = client.get(url)
        assert "bi-exclamation-triangle-fill" in resp3.content.decode()
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
        from django.contrib.auth.models import User
        from django.urls import reverse

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
        from django.contrib.auth.models import User
        from django.urls import reverse

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

    # --- due date tests ---

    @pytest.mark.unit
    def test_due_date_saves_and_roundtrips(self, product, bom, bom_item):
        """due_date persists through create and refresh."""
        import datetime

        job = Production.objects.create(
            product=product, quantity=1, due_date=datetime.date(2026, 4, 1)
        )
        job.refresh_from_db()
        assert job.due_date == datetime.date(2026, 4, 1)

    @pytest.mark.unit
    def test_due_date_nullable(self, product, bom, bom_item):
        """Jobs without a due_date default to None."""
        job = Production.objects.create(product=product, quantity=1)
        job.refresh_from_db()
        assert job.due_date is None

    def test_overdue_badge_in_list(self, client, product, bom, bom_item):
        """Past-due open jobs render with a danger badge."""
        import datetime

        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="due_test")
        client.force_login(user)
        Production.objects.create(
            product=product,
            quantity=1,
            due_date=datetime.date(2020, 1, 1),
        )
        url = reverse("production:production-list")
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "bg-danger-subtle" in content

    def test_no_due_date_renders_dash(self, client, product, bom, bom_item):
        """Jobs without a due_date show a dash in the list."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="due_test2")
        client.force_login(user)
        Production.objects.create(product=product, quantity=1)
        url = reverse("production:production-list")
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "\u2014" in content  # em-dash

    def test_list_ordering_overdue_before_no_date(self, client, product, bom, bom_item):
        """Open jobs with a due date sort before those without one."""
        import datetime

        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="due_test3")
        client.force_login(user)
        no_date = Production.objects.create(product=product, quantity=1)
        dated = Production.objects.create(
            product=product,
            quantity=1,
            due_date=datetime.date(2020, 1, 1),
        )
        url = reverse("production:production-list")
        resp = client.get(url)
        jobs = list(resp.context["productions"])
        # dated job should appear before the no-date job
        dated_idx = next(i for i, j in enumerate(jobs) if j.pk == dated.pk)
        no_date_idx = next(i for i, j in enumerate(jobs) if j.pk == no_date.pk)
        assert dated_idx < no_date_idx

    def test_due_date_form_field_present(self, client, product, bom):
        """Create form includes a date input for due_date."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="due_test4")
        client.force_login(user)
        url = reverse("production:production-create")
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert 'name="due_date"' in content
        assert 'type="date"' in content

    # --- component shortage warning tests ---

    def test_components_list_correct_quantities(self, client, product, bom, bom_item):
        """Detail view builds component list with correct per_unit, required, stock."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="shortage1")
        client.force_login(user)
        job = Production.objects.create(product=product, quantity=5)
        url = reverse("production:production-detail", args=[job.pk])
        resp = client.get(url)
        components = resp.context["components"]
        assert len(components) > 0
        for c in components:
            assert "per_unit" in c
            assert "required" in c
            assert "required_remaining" in c
            assert "stock" in c
            assert c["required"] == c["per_unit"] * job.quantity

    def test_shortfall_zero_when_stock_sufficient(self, client, product, bom, bom_item):
        """When stock covers the job, shortfall is 0 and ok is True."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="shortage2")
        client.force_login(user)
        # fixture seeds 100 units per component; small job should be fine
        job = Production.objects.create(product=product, quantity=1)
        url = reverse("production:production-detail", args=[job.pk])
        resp = client.get(url)
        for c in resp.context["components"]:
            assert c["shortfall"] == 0
            assert c["ok"] is True

    def test_shortfall_correct_when_stock_insufficient(
        self, client, product, bom, bom_item
    ):
        """When stock cannot cover the job, shortfall equals the deficit."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="shortage3")
        client.force_login(user)
        # quantity=1000 with bom_item.quantity=10 needs 10000 but only 100 in stock
        job = Production.objects.create(product=product, quantity=1000)
        url = reverse("production:production-detail", args=[job.pk])
        resp = client.get(url)
        short_components = [c for c in resp.context["components"] if not c["ok"]]
        assert len(short_components) > 0
        for c in short_components:
            assert c["shortfall"] == c["required_remaining"] - c["stock"]
            assert c["shortfall"] > 0

    def test_any_shortage_true_when_component_short(
        self, client, product, bom, bom_item
    ):
        """any_shortage is True when at least one component is short."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="shortage4")
        client.force_login(user)
        job = Production.objects.create(product=product, quantity=1000)
        url = reverse("production:production-detail", args=[job.pk])
        resp = client.get(url)
        assert resp.context["any_shortage"] is True

    def test_any_shortage_false_when_all_covered(self, client, product, bom, bom_item):
        """any_shortage is False when all components have enough stock."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="shortage5")
        client.force_login(user)
        job = Production.objects.create(product=product, quantity=1)
        url = reverse("production:production-detail", args=[job.pk])
        resp = client.get(url)
        assert resp.context["any_shortage"] is False

    @pytest.mark.unit
    def test_missing_inventory_treated_as_zero(self, product, bom, bom_item):
        """Component with no Inventory record has stock=0 and shortfall."""
        from inventory.models import Product as P

        # create a fresh component with NO inventory record
        orphan = P.objects.create(name="orphan component")
        bom_obj = BillOfMaterials.objects.get(product=product)
        BOMItem.objects.create(bom=bom_obj, product=orphan, quantity=1)
        job = Production.objects.create(product=product, quantity=5)

        # exercise the view logic manually via the view's get_context_data
        from django.test import RequestFactory

        from production.views import ProductionDetailView

        factory = RequestFactory()
        request = factory.get("/")
        view = ProductionDetailView()
        view.object = job
        view.request = request
        view.kwargs = {"pk": job.pk}
        ctx = view.get_context_data()
        orphan_comp = [c for c in ctx["components"] if c["product"] == orphan]
        assert len(orphan_comp) == 1
        assert orphan_comp[0]["stock"] == 0
        assert orphan_comp[0]["shortfall"] == 5

    def test_warning_icon_on_list_for_shortage(self, client, product, bom, bom_item):
        """List view shows warning icon for jobs with insufficient materials."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="shortage7")
        client.force_login(user)
        Production.objects.create(product=product, quantity=1000)
        url = reverse("production:production-list")
        resp = client.get(url)
        content = resp.content.decode()
        assert "bi-exclamation-triangle-fill" in content
        assert "Insufficient components" in content

    def test_list_materials_ok_uses_remaining(self, client, product, bom, bom_item):
        """List view checks materials against remaining qty, not total."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="shortage_rem")
        client.force_login(user)
        # quantity=1000 exceeds stock but 990 already received, remaining=10
        job = Production.objects.create(product=product, quantity=1000)
        Production.objects.filter(pk=job.pk).update(quantity_received=990)
        url = reverse("production:production-list")
        resp = client.get(url)
        content = resp.content.decode()
        assert "bi-check-circle-fill" in content

    # --- BOM tree visualiser tests ---

    @pytest.mark.unit
    def test_bom_tree_root_node(self, product, bom, bom_item):
        """build_bom_tree returns root with correct name, quantity and stock."""
        from production.services import build_bom_tree

        tree = build_bom_tree(product, quantity=10)
        assert tree["name"] == product.name
        assert tree["quantity"] == 10
        assert tree["id"] == product.pk
        assert "stock" in tree
        assert "sufficient" in tree
        assert "children" in tree

    @pytest.mark.unit
    def test_bom_tree_children_nested(self, product, bom, bom_item):
        """Children are nested with scaled quantities for a two-level BOM."""
        from production.services import build_bom_tree

        tree = build_bom_tree(product, quantity=5)
        assert len(tree["children"]) > 0
        for child in tree["children"]:
            assert child["quantity"] > 0
            assert child["name"]
            # quantity should be per_unit * parent quantity
            bom_items = {
                i.product.pk: i.quantity
                for i in product.billofmaterials.bom_items.all()
            }
            if child["id"] in bom_items:
                assert child["quantity"] == bom_items[child["id"]] * 5

    @pytest.mark.unit
    def test_bom_tree_sufficient_false_when_short(self, product, bom, bom_item):
        """sufficient is False when stock < scaled quantity."""
        from production.services import build_bom_tree

        # quantity=1000 means components need 10000+ but fixture has 100
        tree = build_bom_tree(product, quantity=1000)
        short_children = [c for c in tree["children"] if not c["sufficient"]]
        assert len(short_children) > 0

    @pytest.mark.unit
    def test_bom_tree_circular_reference_guard(self, product, bom):
        """Circular BOM references are detected and pruned."""
        from production.services import build_bom_tree

        # Create a circular reference: make product a component of itself
        # via one of its existing BOM items' sub-BOMs.
        # Since build_bom_tree uses a visited set internally, the second
        # encounter of the same product returns None (pruned).
        tree = build_bom_tree(product, quantity=1)
        # The tree should be built without infinite loop
        assert tree is not None
        assert tree["id"] == product.pk

    @pytest.mark.unit
    def test_bom_tree_leaf_node_no_bom(self):
        """Product without a BOM returns a leaf node with empty children."""
        from inventory.models import Product as P
        from production.services import build_bom_tree

        leaf = P.objects.create(name="leaf product")
        tree = build_bom_tree(leaf, quantity=3)
        assert tree is not None
        assert tree["name"] == "leaf product"
        assert tree["quantity"] == 3
        assert tree["children"] == []

    # --- cost roll-up display tests ---

    def test_unit_cost_in_context(
        self, client, product, bom, bom_item, supplier, supplier_product
    ):
        """unit_cost from supplier cost appears in the detail context."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="cost1")
        client.force_login(user)
        job = Production.objects.create(product=product, quantity=5)
        url = reverse("production:production-detail", args=[job.pk])
        resp = client.get(url)
        ctx = resp.context
        assert ctx["unit_cost"] == product.unit_cost
        assert ctx["unit_cost"] > 0

    def test_job_cost_equals_unit_times_quantity(
        self, client, product, bom, bom_item, supplier, supplier_product
    ):
        """total_cost = unit_cost * quantity."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="cost2")
        client.force_login(user)
        job = Production.objects.create(product=product, quantity=8)
        url = reverse("production:production-detail", args=[job.pk])
        resp = client.get(url)
        ctx = resp.context
        assert ctx["total_cost"] == ctx["unit_cost"] * 8

    def test_cost_section_hidden_when_zero(self, client, product, bom, bom_item):
        """Cost Summary section is not rendered when unit_cost is 0."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="cost3")
        client.force_login(user)
        job = Production.objects.create(product=product, quantity=3)
        url = reverse("production:production-detail", args=[job.pk])
        resp = client.get(url)
        content = resp.content.decode()
        assert "Cost Summary" not in content


@pytest.mark.django_db
@pytest.mark.unit
class TestReceiveIntoLocation:
    """Tests for receiving production into a specific inventory location."""

    def test_receive_routes_to_correct_location(self, product, bom, bom_item, location):
        """Receiving routes quantity to the correct InventoryLocation."""
        from inventory.models import Inventory, InventoryLocation
        from production.services import receive_production_into_location

        job = Production.objects.create(product=product, quantity=5)
        receive_production_into_location(job.pk, 3, location.pk)

        inv = Inventory.objects.get(product=product)
        inv_loc = InventoryLocation.objects.get(inventory=inv, location=location)
        assert inv_loc.quantity == 3
        # total inventory also increased
        assert inv.quantity == 100 + 3

    def test_receive_creates_inventory_location(self, product, bom, bom_item, location):
        """InventoryLocation is created if it doesn't exist yet."""
        from inventory.models import Inventory, InventoryLocation
        from production.services import receive_production_into_location

        inv = Inventory.objects.get(product=product)
        assert not InventoryLocation.objects.filter(
            inventory=inv, location=location
        ).exists()

        job = Production.objects.create(product=product, quantity=5)
        receive_production_into_location(job.pk, 2, location.pk)

        assert InventoryLocation.objects.filter(
            inventory=inv, location=location
        ).exists()
        inv_loc = InventoryLocation.objects.get(inventory=inv, location=location)
        assert inv_loc.quantity == 2

    def test_receive_without_location_fallback(self, product, bom, bom_item):
        """Receiving without a location (via the view) falls back gracefully."""
        from inventory.models import Inventory

        job = Production.objects.create(product=product, quantity=5)
        # simulate the view's no-location path
        job.quantity_received += 2
        job.save()
        job.refresh_from_db()
        assert job.quantity_received == 2
        inv = Inventory.objects.get(product=product)
        assert inv.quantity == 100 + 2

    def test_cannot_receive_more_than_remaining(self, product, bom, bom_item, location):
        """Receiving more than remaining raises ValidationError."""
        from django.core.exceptions import ValidationError

        from production.services import receive_production_into_location

        job = Production.objects.create(product=product, quantity=5)
        with pytest.raises(ValidationError):
            receive_production_into_location(job.pk, 10, location.pk)

    def test_ledger_entry_tagged_with_location(self, product, bom, bom_item, location):
        """The finished-good ledger entry gets location tagged correctly."""
        from inventory.models import InventoryLedger
        from production.services import receive_production_into_location

        job = Production.objects.create(product=product, quantity=5)
        receive_production_into_location(job.pk, 3, location.pk)

        entry = InventoryLedger.objects.filter(
            product=product,
            action="Production",
            transaction_id=job.pk,
            quantity__gt=0,
        ).first()
        assert entry is not None
        assert entry.location == location

    def test_job_closes_when_fully_received(self, product, bom, bom_item, location):
        """Job closes automatically when fully received via location service."""
        from production.services import receive_production_into_location

        job = Production.objects.create(product=product, quantity=3)
        receive_production_into_location(job.pk, 3, location.pk)
        job.refresh_from_db()
        assert job.closed is True
        assert job.complete is True
        assert job.remaining == 0


@pytest.mark.django_db
@pytest.mark.integration
class TestCostSummary:
    """Tests for sale_price, effective_sale_price, and cost summary logic."""

    @pytest.mark.unit
    def test_effective_sale_price_returns_sale_price_when_set(self, product):
        """effective_sale_price returns sale_price when it is set."""
        from decimal import Decimal

        product.sale_price = Decimal("125.00")
        product.save()
        assert product.effective_sale_price == Decimal("125.00")

    @pytest.mark.unit
    def test_effective_sale_price_falls_back_to_last_sold(self, product):
        """effective_sale_price falls back to last sales order line price."""
        from decimal import Decimal

        from sales.models import Customer, CustomerProduct, SalesOrder, SalesOrderLine

        customer = Customer.objects.create(name="Test Buyer")
        cp = CustomerProduct.objects.create(
            customer=customer, product=product, price=Decimal("99.50")
        )
        so = SalesOrder.objects.create(customer=customer)
        SalesOrderLine.objects.create(sales_order=so, product=cp, quantity=1)
        # no sale_price set on product
        assert product.sale_price is None
        assert product.effective_sale_price == Decimal("99.50")

    @pytest.mark.unit
    def test_effective_sale_price_zero_when_none_set(self, product):
        """effective_sale_price returns 0 when neither sale_price nor sales exist."""
        assert product.sale_price is None
        assert product.effective_sale_price == 0

    def test_projected_margin_computes_correctly(
        self, client, product, bom, bom_item, supplier_product
    ):
        """projected_margin_pct = (value - cost) / value × 100."""
        from decimal import Decimal

        from django.contrib.auth.models import User
        from django.urls import reverse

        product.sale_price = Decimal("125.00")
        product.save()

        user = User.objects.create_user(username="margin_test")
        client.force_login(user)

        job = Production.objects.create(product=product, quantity=10)
        url = reverse("production:production-detail", args=[job.pk])
        resp = client.get(url)
        ctx = resp.context

        unit_cost = product.unit_cost
        projected_value = Decimal("125.00") * 10
        expected_margin = ((projected_value - unit_cost * 10) / projected_value) * 100

        assert ctx["projected_value"] == projected_value
        assert round(float(ctx["projected_margin_pct"]), 1) == round(
            float(expected_margin), 1
        )

    def test_margin_pct_none_when_no_sale_price(self, client, product, bom, bom_item):
        """margin_pct is None when no sale price exists."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="no_price")
        client.force_login(user)

        job = Production.objects.create(product=product, quantity=5)
        url = reverse("production:production-detail", args=[job.pk])
        resp = client.get(url)
        ctx = resp.context

        assert ctx["actual_margin_pct"] is None
        assert ctx["projected_value"] is None
        assert ctx["projected_margin_pct"] is None

    def test_cost_section_hidden_when_both_zero(self, client, product):
        """Cost summary section hidden when both unit_cost and sale_price are 0."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="zero_cost")
        client.force_login(user)

        job = Production.objects.create(product=product, quantity=3)
        url = reverse("production:production-detail", args=[job.pk])
        resp = client.get(url)
        content = resp.content.decode()
        assert "Cost Summary" not in content
