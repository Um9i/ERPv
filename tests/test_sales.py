import pytest

from inventory.models import Inventory, InventoryLedger
from sales.models import SalesLedger


@pytest.mark.django_db
class TestCustomer:
    def test_customer_creation(self, customer):
        assert customer.name == "Test Customer"

    def test_customer_contact_creation(self, customer_contact):
        assert customer_contact.name == "Test Contact"

    def test_customer_detail_context(self, client, customer, customer_product):
        from django.contrib.auth.models import User
        from django.urls import reverse

        from sales.models import SalesOrder

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        # create one order so the "see all" link is shown
        SalesOrder.objects.create(customer=customer)

        url = reverse("sales:customer-detail", args=[customer.pk])
        response = client.get(url)
        assert response.status_code == 200
        products_page = response.context.get("customer_products")
        assert products_page is not None
        assert customer_product in products_page.object_list
        assert "sales_orders" in response.context
        orders_page = response.context.get("sales_orders")
        assert hasattr(orders_page, "paginator")
        content = response.content.decode()
        assert (
            f'href="{reverse("sales:customer-salesorders", args=[customer.pk])}"'
            in content
        )
        assert (
            f'href="{reverse("sales:customer-products", args=[customer.pk])}"'
            in content
        )

    def test_customer_contacts_shown_and_links(
        self, client, customer, customer_contact
    ):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester2")
        client.force_login(user)
        url = reverse("sales:customer-detail", args=[customer.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Contacts" in content
        assert customer_contact.name in content
        assert "customer-contacts/create" in content
        assert f"customer-contacts/{customer_contact.pk}/update" in content
        assert f"customer-contacts/{customer_contact.pk}/delete" in content

    def test_customer_contact_create_from_form(self, client, customer):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester3")
        client.force_login(user)
        url = reverse("sales:customer-contact-create") + f"?customer={customer.pk}"
        resp = client.get(url)
        assert resp.status_code == 200
        data = {"customer": customer.pk, "name": "New C", "email": "a@b.com"}
        resp2 = client.post(url, data)
        assert resp2.status_code == 302
        assert resp2.url == reverse("sales:customer-detail", args=[customer.pk])
        resp3 = client.get(resp2.url)
        assert "New C" in resp3.content.decode()

    def test_customer_contact_edit_and_delete(self, client, customer, customer_contact):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester4")
        client.force_login(user)
        # edit
        url = reverse("sales:customer-contact-update", args=[customer_contact.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        data = {
            "customer": customer.pk,
            "name": "Edited Cust",
            "email": customer_contact.email,
        }
        resp2 = client.post(url, data)
        assert resp2.status_code == 302
        assert resp2.url == reverse("sales:customer-detail", args=[customer.pk])
        customer_contact.refresh_from_db()
        assert customer_contact.name == "Edited Cust"
        # delete
        del_url = reverse("sales:customer-contact-delete", args=[customer_contact.pk])
        resp3 = client.post(del_url)
        assert resp3.status_code == 302
        assert resp3.url == reverse("sales:customer-detail", args=[customer.pk])
        from sales.models import CustomerContact

        assert not CustomerContact.objects.filter(pk=customer_contact.pk).exists()

    def test_customer_list_pagination(self, client, customer):
        from django.contrib.auth.models import User
        from django.urls import reverse

        from sales.models import Customer

        user = User.objects.create_user(username="tester")
        client.force_login(user)
        for i in range(25):
            Customer.objects.create(name=f"C{i}")
        url = reverse("sales:customer-list")
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp.context["page_obj"].paginator is not None
        resp2 = client.get(url + "?page=2")
        assert resp2.status_code == 200

    def test_customer_list_search(self, client, customer):
        from django.contrib.auth.models import User
        from django.urls import reverse

        from sales.models import Customer

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        Customer.objects.create(name="Alpha Corp")
        Customer.objects.create(name="Beta LLC")
        url = reverse("sales:customer-list")
        resp = client.get(url, {"q": "Alpha"})
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Alpha Corp" in content
        assert "Beta LLC" not in content
        resp2 = client.get(url, {"q": ""})
        assert customer.name in resp2.content.decode()

    def test_dashboard_metrics(self, client, customer, sales_order, sales_order_line):
        """Dashboard should provide counts that match DB state."""
        import datetime

        from django.contrib.auth.models import User
        from django.urls import reverse

        from sales.models import SalesOrder

        # give the fixture order a ship_by_date of today so it appears in today's totals
        today = datetime.date.today()
        sales_order.ship_by_date = today
        sales_order.save(update_fields=["ship_by_date"])

        user = User.objects.create_user(username="dashuser")
        client.force_login(user)
        url = reverse("sales:sales-dashboard")
        resp = client.get(url)
        assert resp.status_code == 200
        ctx = resp.context
        assert ctx["total_orders"] == SalesOrder.objects.count()
        due_qs = SalesOrder.objects.filter(ship_by_date__lte=today)
        assert (
            ctx["shipped_orders"]
            == due_qs.filter(sales_order_lines__quantity_shipped__gt=0)
            .distinct()
            .count()
        )
        assert (
            ctx["pending_shipping"]
            == due_qs.filter(sales_order_lines__complete=False).distinct().count()
        )
        assert ctx["total_customers"] == customer.__class__.objects.count()
        content = resp.content.decode()
        assert "Total Orders" in content
        assert "Shipped" in content
        assert "Pending Shipping" in content
        assert "Customers" in content


@pytest.mark.django_db
class TestCustomerProduct:
    def test_customer_product_creation(self, customer_product):
        assert customer_product.price == 10.00

    def test_customer_product_create_title(self, client, customer):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        url = reverse("sales:customer-product-create")
        resp = client.get(url)
        assert resp.status_code == 200
        assert "New Customer Product" in resp.content.decode()

    def test_customer_product_update_title(self, client, customer_product):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        url = reverse("sales:customer-product-update", args=[customer_product.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        assert "Edit Customer Product" in resp.content.decode()

    def test_on_sales_order(self, customer_product, sales_order_line):
        assert customer_product.on_sales_order() == 5


@pytest.mark.django_db
class TestSalesOrder:
    def test_sales_order_creation(self, sales_order):
        assert sales_order.customer.name == "Test Customer"

    def test_sales_order_list_pagination(self, client, sales_order):
        from django.contrib.auth.models import User
        from django.urls import reverse

        from sales.models import SalesOrder

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        for i in range(12):
            SalesOrder.objects.create(customer=sales_order.customer)
        url = reverse("sales:sales-order-list")
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp.context["sales_orders"].paginator is not None
        resp2 = client.get(url + "?page=2")
        assert resp2.status_code == 200

    def test_sales_order_list_search(self, client, customer, sales_order):
        from django.contrib.auth.models import User
        from django.urls import reverse

        from sales.models import Customer, SalesOrder

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        other = Customer.objects.create(name="Other Customer")
        SalesOrder.objects.create(customer=other)
        url = reverse("sales:sales-order-list")
        resp = client.get(url, {"q": "Test Customer", "status": ""})
        content = resp.content.decode()
        assert sales_order.customer.name in content
        assert "Other Customer" not in content
        resp2 = client.get(url, {"q": str(sales_order.pk), "status": ""})
        assert sales_order.order_number in resp2.content.decode()

    def test_sales_order_properties(self, sales_order, sales_order_line):
        assert sales_order.order_number.startswith("SO")
        assert sales_order.date == sales_order.created_at
        assert sales_order.status == "Open"
        expected = sales_order_line.product.price * sales_order_line.quantity
        from decimal import ROUND_HALF_UP, Decimal

        expected = Decimal(expected).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert sales_order.total_amount == expected
        sales_order_line.complete = True
        sales_order_line.quantity_shipped = sales_order_line.quantity
        sales_order_line.save()
        assert sales_order.status == "Closed"
        assert sales_order.total_amount == expected

    def test_remaining_and_order_values(self, sales_order_line):
        so = sales_order_line.sales_order
        assert so.remaining_total == so.total_amount
        original_total = so.total_amount
        assert sales_order_line.shipped_total == 0
        assert (
            sales_order_line.remaining_total
            == sales_order_line.unit_price * sales_order_line.quantity
        )
        sales_order_line.quantity_shipped = 2
        sales_order_line.save()
        assert so.total_amount == original_total
        expected_rem = (sales_order_line.quantity - 2) * sales_order_line.unit_price
        assert sales_order_line.remaining_total == expected_rem
        assert so.remaining_total == expected_rem

    def test_sales_order_detail_shows_shipped(self, client, sales_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        so = sales_order_line.sales_order
        sales_order_line.quantity_shipped = 3
        sales_order_line.save()
        url = reverse("sales:sales-order-detail", args=[so.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert str(sales_order_line.quantity_shipped) in content
        assert str(sales_order_line.shipped_total) in content
        assert str(sales_order_line.remaining_total) in content

    def test_can_close_order_from_list(self, client, sales_order_line):
        """List page shows close button; closing still posts to detail URL."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        from inventory.models import Inventory

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        so = sales_order_line.sales_order
        list_url = reverse("sales:sales-order-list")
        resp = client.get(list_url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert 'name="close_order"' in content

        detail_url = reverse("sales:sales-order-detail", args=[so.pk])
        resp2 = client.post(detail_url, {"close_order": "1"})
        assert resp2.status_code == 302
        assert resp2.url == detail_url
        so.refresh_from_db()
        assert so.status == "Closed"

        for line in so.sales_order_lines.all():
            assert line.complete is True
            assert line.closed is True
            assert line.quantity_shipped == 0
            assert line.value is None
        inv = Inventory.objects.filter(product=sales_order_line.product.product).first()
        assert inv is None or inv.quantity == 100

        # list page should no longer show close button for closed order
        resp3 = client.get(list_url)
        assert 'name="close_order"' not in resp3.content.decode()

    def test_create_view_prefills_and_filters(self, client, customer, customer_product):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        url = reverse("sales:sales-order-create") + f"?customer={customer.pk}"
        response = client.get(url)
        assert response.status_code == 200
        # MANAGEMENT FORM should use sales_order_lines prefix so JS can add rows
        assert 'id="id_sales_order_lines-TOTAL_FORMS"' in response.content.decode()
        form = response.context["form"]
        assert str(form.initial.get("customer")) == str(customer.pk)
        from django import forms

        assert isinstance(form.fields["customer"].widget, forms.HiddenInput)
        fs = response.context["lines_formset"]
        for f in fs:
            assert "complete" not in f.fields
            assert "DELETE" in f.fields
            qs = f.fields["product"].queryset
            assert list(qs) == list(customer.customer_products.all())

    def test_customer_product_create_prefills_customer(self, client, customer, product):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        url = reverse("sales:customer-product-create") + f"?customer={customer.pk}"
        response = client.get(url)
        assert response.status_code == 200
        form = response.context["form"]
        assert str(form.initial.get("customer")) == str(customer.pk)
        from django import forms

        assert isinstance(form.fields["customer"].widget, forms.HiddenInput)

        post_url = reverse("sales:customer-product-create")
        data = {"customer": customer.pk, "product": product.pk, "price": "5.00"}
        resp2 = client.post(post_url, data)
        assert resp2.status_code == 302
        assert resp2.url == reverse("sales:customer-detail", args=[customer.pk])

    def test_create_view_auto_customer_and_lines(
        self, client, customer, customer_product
    ):
        from django.contrib.auth.models import User
        from django.urls import reverse

        from sales.models import SalesOrder

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        url = reverse("sales:sales-order-create") + f"?customer={customer.pk}"
        prefix = "sales_order_lines"
        data = {
            "customer": customer.pk,
            f"{prefix}-TOTAL_FORMS": "2",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
            f"{prefix}-0-product": customer_product.pk,
            f"{prefix}-0-quantity": "3",
            f"{prefix}-1-product": customer_product.pk,
            f"{prefix}-1-quantity": "4",
        }
        response = client.post(url, data)
        assert response.status_code == 302
        so = SalesOrder.objects.latest("pk")
        assert so.customer == customer
        lines = so.sales_order_lines.all()
        assert lines.count() == 2
        first, second = lines.order_by("pk")
        assert first.product == customer_product
        assert first.quantity == 3
        assert second.product == customer_product
        assert second.quantity == 4

    def test_create_view_rejects_mismatched_product(
        self, client, customer, customer_product, product
    ):
        from django.contrib.auth.models import User
        from django.urls import reverse

        from sales.models import Customer, CustomerProduct, SalesOrder

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        other_customer = Customer.objects.create(name="OtherCust")
        other_cp = CustomerProduct.objects.create(
            customer=other_customer,
            product=product,
            price=7.00,
        )
        url = reverse("sales:sales-order-create") + f"?customer={customer.pk}"
        prefix = "sales_order_lines"
        data = {
            "customer": customer.pk,
            f"{prefix}-TOTAL_FORMS": "1",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
            # deliberately supply the other customer's product id
            f"{prefix}-0-product": other_cp.pk,
            f"{prefix}-0-quantity": "5",
        }
        response = client.post(url, data)
        assert response.status_code == 200
        fs = response.context["lines_formset"]
        assert not fs.is_valid()
        assert not SalesOrder.objects.filter(customer=customer).exists()

    def test_create_view_rejects_empty_order(self, client, customer):
        """Submitting a sales order with no line items should fail validation."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        from sales.models import SalesOrder

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        url = reverse("sales:sales-order-create") + f"?customer={customer.pk}"
        prefix = "sales_order_lines"
        data = {
            "customer": customer.pk,
            f"{prefix}-TOTAL_FORMS": "1",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
            # leave the single extra form completely blank
        }
        response = client.post(url, data)
        assert response.status_code == 200
        fs = response.context["lines_formset"]
        assert not fs.is_valid()
        assert "A sales order must have at least one line item." in fs.non_form_errors()
        assert not SalesOrder.objects.filter(customer=customer).exists()

    def test_sales_order_form_js_syntax(self, client, customer):
        """Validate the order_form.js static file is referenced and compiles."""
        import subprocess
        from pathlib import Path

        from django.conf import settings
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="js3")
        client.force_login(user)
        url = reverse("sales:sales-order-create")
        resp = client.get(url)
        assert resp.status_code == 200
        html = resp.content.decode()
        assert "order_form.js" in html
        js_path = Path(settings.BASE_DIR) / "static" / "js" / "order_form.js"
        if not js_path.exists():
            pytest.skip("Compiled JS not present (run tsc first)")
        result = subprocess.run(
            ["node", "--check", str(js_path)], capture_output=True, text=True
        )
        assert result.returncode == 0, f"JS syntax error: {result.stderr}"


@pytest.mark.django_db
class TestSalesOrderLine:
    def test_sales_order_line_creation(self, sales_order_line):
        assert sales_order_line.quantity == 5

    def test_sales_order_line_save(self, sales_order_line_complete):
        inventory = Inventory.objects.get(
            product=sales_order_line_complete.product.product
        )
        assert inventory.quantity == 0
        ledger = (
            InventoryLedger.objects.filter(
                product=sales_order_line_complete.product.product
            )
            .order_by("pk")
            .first()
        )
        assert ledger is not None
        assert ledger.quantity == -5
        sales_ledger = SalesLedger.objects.get(
            product=sales_order_line_complete.product.product
        )
        assert sales_ledger.quantity == 5


@pytest.mark.django_db
class TestShipping:
    def test_ship_view_marks_lines(self, client, sales_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        from inventory.models import Inventory, InventoryLedger

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        so = sales_order_line.sales_order
        list_url = reverse("sales:sales-order-list")
        # list should expose ship button for open order
        list_resp = client.get(list_url)
        assert "Ship" in list_resp.content.decode()
        url = reverse("sales:sales-order-ship", args=[so.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Already Shipped" in content or "Quantity Shipped" in content
        assert "ship_all" in content
        assert f'max="{sales_order_line.remaining}"' in content
        data = {f"shipped_{sales_order_line.id}": sales_order_line.quantity}
        resp2 = client.post(url, data)
        assert resp2.status_code == 302
        assert resp2.url == reverse("sales:sales-order-list")
        sales_order_line.refresh_from_db()
        assert sales_order_line.complete is True
        assert sales_order_line.quantity_shipped == sales_order_line.quantity
        assert (
            sales_order_line.value
            == sales_order_line.unit_price * sales_order_line.quantity
        )
        so.refresh_from_db()
        assert so.updated_at > so.created_at
        resp3 = client.get(url)
        assert str(sales_order_line.quantity_shipped) in resp3.content.decode()
        inv = Inventory.objects.get(product=sales_order_line.product.product)
        # fixture ensures starting stock = 100
        assert inv.quantity == 100 - sales_order_line.quantity
        ledger = (
            InventoryLedger.objects.filter(product=sales_order_line.product.product)
            .order_by("pk")
            .last()
        )
        assert ledger.quantity == -sales_order_line.quantity

    def test_ship_view_partial_quantity(self, client, sales_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        from inventory.models import Inventory, InventoryLedger

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        so = sales_order_line.sales_order
        url = reverse("sales:sales-order-ship", args=[so.pk])
        partial = sales_order_line.quantity - 1
        data = {f"shipped_{sales_order_line.id}": partial}
        resp = client.post(url, data)
        assert resp.status_code == 302
        sales_order_line.refresh_from_db()
        assert sales_order_line.complete is False
        assert sales_order_line.closed is False
        assert sales_order_line.quantity_shipped == partial
        assert sales_order_line.value is None
        so.refresh_from_db()
        remaining = sales_order_line.quantity - partial
        resp2 = client.get(url)
        assert f'max="{remaining}"' in resp2.content.decode()
        inv = Inventory.objects.get(product=sales_order_line.product.product)
        assert inv.quantity == 100 - partial
        ledger = (
            InventoryLedger.objects.filter(product=sales_order_line.product.product)
            .order_by("pk")
            .last()
        )
        assert ledger.quantity == -partial

    def test_ship_all_button(self, client, customer, customer_product):
        from django.contrib.auth.models import User
        from django.urls import reverse

        from inventory.models import Inventory, InventoryLedger
        from sales.models import SalesOrder, SalesOrderLine

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        # ensure inventory on product so shipping succeeds
        Inventory.objects.update_or_create(
            product=customer_product.product, defaults={"quantity": 100}
        )
        so = SalesOrder.objects.create(customer=customer)
        line1 = SalesOrderLine.objects.create(
            sales_order=so, product=customer_product, quantity=3
        )
        line2 = SalesOrderLine.objects.create(
            sales_order=so, product=customer_product, quantity=5
        )
        url = reverse("sales:sales-order-ship", args=[so.pk])
        resp = client.post(url, {"ship_all": "1"})
        assert resp.status_code == 302
        line1.refresh_from_db()
        line2.refresh_from_db()
        assert line1.quantity_shipped == 3
        assert line2.quantity_shipped == 5
        assert line1.complete
        assert line2.complete
        inv = Inventory.objects.get(product=customer_product.product)
        # started at 100 for every product in fixtures
        assert inv.quantity == 100 - 8
        ledger = (
            InventoryLedger.objects.filter(product=customer_product.product)
            .order_by("pk")
            .last()
        )
        assert ledger.quantity in (-5, -3)
        getresp = client.get(url)
        assert 'max="0"' in getresp.content.decode()


@pytest.mark.django_db
class TestPickConfirmation:
    """Tests for the scan-to-pick confirmation workflow."""

    def _make_pick_list(self, sales_order_line):
        """Create a pick list with one line for the given sales order line."""
        from sales.models import PickList, PickListLine

        pick_list = PickList.objects.create(sales_order=sales_order_line.sales_order)
        line = PickListLine.objects.create(
            pick_list=pick_list,
            sales_order_line=sales_order_line,
            location=None,
            quantity=sales_order_line.quantity,
        )
        return pick_list, line

    def test_pick_confirm_get(self, client, sales_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        pick_list, _ = self._make_pick_list(sales_order_line)
        url = reverse("sales:pick-confirm", args=[pick_list.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Pick Confirmation" in content
        assert "0 / 1 confirmed" in content

    def test_pick_confirm_manual_line(self, client, sales_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        pick_list, line = self._make_pick_list(sales_order_line)
        url = reverse("sales:pick-confirm", args=[pick_list.pk])
        resp = client.post(
            url,
            {"line_id": str(line.pk)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["line_id"] == line.pk
        assert data["all_confirmed"] is True

        line.refresh_from_db()
        assert line.confirmed is True
        assert line.confirmed_at is not None

    def test_pick_confirm_scan_barcode(self, client, sales_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        product = sales_order_line.product.product
        product.barcode = "TEST-BARCODE-123"
        product.save(update_fields=["barcode"])

        pick_list, line = self._make_pick_list(sales_order_line)
        url = reverse("sales:pick-confirm", args=[pick_list.pk])
        resp = client.post(
            url,
            {"scan_value": "TEST-BARCODE-123"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["product_name"] == product.name

        line.refresh_from_db()
        assert line.confirmed is True

    def test_pick_confirm_scan_sku(self, client, sales_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        product = sales_order_line.product.product
        product.sku = "SKU-999"
        product.save(update_fields=["sku"])

        pick_list, line = self._make_pick_list(sales_order_line)
        url = reverse("sales:pick-confirm", args=[pick_list.pk])
        resp = client.post(
            url,
            {"scan_value": "SKU-999"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        line.refresh_from_db()
        assert line.confirmed is True

    def test_pick_confirm_scan_no_match(self, client, sales_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        pick_list, _ = self._make_pick_list(sales_order_line)
        url = reverse("sales:pick-confirm", args=[pick_list.pk])
        resp = client.post(
            url,
            {"scan_value": "UNKNOWN-CODE"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "No product matches" in data["error"]

    def test_pick_confirm_scan_already_confirmed(self, client, sales_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        product = sales_order_line.product.product
        product.barcode = "BC-DONE"
        product.save(update_fields=["barcode"])

        pick_list, line = self._make_pick_list(sales_order_line)
        line.confirmed = True
        line.save(update_fields=["confirmed"])

        url = reverse("sales:pick-confirm", args=[pick_list.pk])
        resp = client.post(
            url,
            {"scan_value": "BC-DONE"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        data = resp.json()
        assert data["ok"] is False
        assert "no unconfirmed lines" in data["error"].lower()

    def test_pick_confirm_invalid_line_id(self, client, sales_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        pick_list, _ = self._make_pick_list(sales_order_line)
        url = reverse("sales:pick-confirm", args=[pick_list.pk])
        resp = client.post(
            url,
            {"line_id": "99999"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        data = resp.json()
        assert data["ok"] is False
        assert "not found" in data["error"].lower()

    def test_pick_confirm_reset(self, client, sales_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        pick_list, line = self._make_pick_list(sales_order_line)
        line.confirmed = True
        line.save(update_fields=["confirmed"])

        url = reverse("sales:pick-confirm-reset", args=[pick_list.pk])
        resp = client.post(url)
        assert resp.status_code == 302

        line.refresh_from_db()
        assert line.confirmed is False

    def test_all_confirmed_property(self, sales_order_line):

        pick_list, line = self._make_pick_list(sales_order_line)
        assert pick_list.all_confirmed is False

        line.confirmed = True
        line.save(update_fields=["confirmed"])
        assert pick_list.all_confirmed is True

    def test_qrcode_view_returns_png(self, client, product):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        product.barcode = "QR-TEST"
        product.save(update_fields=["barcode"])

        url = reverse("sales:product-qrcode", args=[product.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp["Content-Type"] == "image/png"
        # PNG magic bytes
        assert resp.content[:4] == b"\x89PNG"

    def test_pick_list_detail_has_scan_link(self, client, sales_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        pick_list, _ = self._make_pick_list(sales_order_line)
        url = reverse("sales:pick-list-detail", args=[pick_list.pk])
        resp = client.get(url)
        content = resp.content.decode()
        confirm_url = reverse("sales:pick-confirm", args=[pick_list.pk])
        assert confirm_url in content
        assert "Scan" in content

    def test_pick_confirm_non_ajax_redirect(self, client, sales_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        pick_list, line = self._make_pick_list(sales_order_line)
        url = reverse("sales:pick-confirm", args=[pick_list.pk])
        # POST without AJAX header should redirect
        resp = client.post(url, {"line_id": str(line.pk)})
        assert resp.status_code == 302

    def test_pick_confirm_requires_login(self, client, sales_order_line):
        from django.urls import reverse

        pick_list, _ = self._make_pick_list(sales_order_line)
        url = reverse("sales:pick-confirm", args=[pick_list.pk])
        resp = client.get(url)
        assert resp.status_code == 302
        assert "/login/" in resp.url or "/accounts/login/" in resp.url
