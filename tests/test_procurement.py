import pytest

from inventory.models import Inventory, InventoryLedger
from procurement.models import PurchaseLedger, PurchaseOrder, PurchaseOrderLine


@pytest.mark.django_db
class TestSupplier:
    def test_supplier_creation(self, supplier):
        assert supplier.name == "Test Supplier"

    def test_supplier_contact_creation(self, supplier_contact):
        assert supplier_contact.name == "Test Contact"

    def test_supplier_detail_context(self, client, supplier, supplier_product):
        from django.contrib.auth.models import User
        from django.urls import reverse

        from procurement.models import PurchaseOrder

        # login before accessing protected pages
        user = User.objects.create_user(username="tester")
        client.force_login(user)

        # create one purchase order so the "see all" link is shown
        PurchaseOrder.objects.create(supplier=supplier)

        url = reverse("procurement:supplier-detail", args=[supplier.pk])
        response = client.get(url)
        assert response.status_code == 200
        # supplier_products is now a page object
        products_page = response.context.get("supplier_products")
        assert products_page is not None
        assert supplier_product in products_page.object_list
        # purchase_orders also should be a page object, now non‑empty
        assert "purchase_orders" in response.context
        purchase_page = response.context.get("purchase_orders")
        assert hasattr(purchase_page, "paginator")
        # see all links present in rendered content
        content = response.content.decode()
        assert (
            f'href="{reverse("procurement:supplier-purchaseorders", args=[supplier.pk])}"'
            in content
        )
        assert (
            f'href="{reverse("procurement:supplier-products", args=[supplier.pk])}"'
            in content
        )

    def test_supplier_contacts_shown_and_links(
        self, client, supplier, supplier_contact
    ):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester2")
        client.force_login(user)
        url = reverse("procurement:supplier-detail", args=[supplier.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Contacts" in content
        assert supplier_contact.name in content
        assert "supplier-contacts/create" in content
        assert f"supplier-contacts/{supplier_contact.pk}/update" in content
        assert f"supplier-contacts/{supplier_contact.pk}/delete" in content

    def test_supplier_contact_create_from_form(self, client, supplier):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester3")
        client.force_login(user)
        url = (
            reverse("procurement:supplier-contact-create") + f"?supplier={supplier.pk}"
        )
        resp = client.get(url)
        assert resp.status_code == 200
        # post new contact
        data = {
            "supplier": supplier.pk,
            "name": "New Contact",
            "email": "x@example.com",
        }
        resp2 = client.post(url, data)
        assert resp2.status_code == 302
        assert resp2.url == reverse("procurement:supplier-detail", args=[supplier.pk])
        # ensure appears on detail
        resp3 = client.get(resp2.url)
        assert "New Contact" in resp3.content.decode()

    def test_supplier_contact_edit_and_delete(self, client, supplier, supplier_contact):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester4")
        client.force_login(user)
        # edit
        url = reverse("procurement:supplier-contact-update", args=[supplier_contact.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        data = {
            "supplier": supplier.pk,
            "name": "Edited Name",
            "email": supplier_contact.email,
        }
        resp2 = client.post(url, data)
        assert resp2.status_code == 302
        assert resp2.url == reverse("procurement:supplier-detail", args=[supplier.pk])
        supplier_contact.refresh_from_db()
        assert supplier_contact.name == "Edited Name"
        # delete
        del_url = reverse(
            "procurement:supplier-contact-delete", args=[supplier_contact.pk]
        )
        resp3 = client.post(del_url)
        assert resp3.status_code == 302
        assert resp3.url == reverse("procurement:supplier-detail", args=[supplier.pk])
        from procurement.models import SupplierContact

        assert not SupplierContact.objects.filter(pk=supplier_contact.pk).exists()

    def test_supplier_list_pagination(self, client, supplier):
        """Supplier list should paginate when many entries exist."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        from procurement.models import Supplier

        user = User.objects.create_user(username="tester")
        client.force_login(user)
        # create enough extra suppliers to require more than one page
        for i in range(25):
            Supplier.objects.create(name=f"Pagi{i}")
        url = reverse("procurement:supplier-list")
        resp = client.get(url)
        assert resp.status_code == 200
        # paginator exists regardless of page count
        assert resp.context["page_obj"].paginator is not None
        resp2 = client.get(url + "?page=2")
        assert resp2.status_code == 200

    def test_supplier_list_search(self, client, supplier):
        """Search box should filter suppliers by name."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        from procurement.models import Supplier

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        Supplier.objects.create(name="Alpha Corp")
        Supplier.objects.create(name="Beta LLC")
        url = reverse("procurement:supplier-list")
        resp = client.get(url, {"q": "Alpha"})
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Alpha Corp" in content
        assert "Beta LLC" not in content
        # empty search returns everything (ensure original supplier still present)
        resp2 = client.get(url, {"q": ""})
        assert supplier.name in resp2.content.decode()

    def test_dashboard_metrics(
        self, client, supplier, purchase_order, purchase_order_line
    ):
        import datetime

        from django.contrib.auth.models import User
        from django.db.models import Count, F, Q
        from django.urls import reverse

        from procurement.models import PurchaseOrder, Supplier

        # give the fixture PO a due_date of today so it falls in the dashboard filter
        today = datetime.date.today()
        purchase_order.due_date = today
        purchase_order.save(update_fields=["due_date"])

        user = User.objects.create_user(username="dashuser")
        client.force_login(user)
        url = reverse("procurement:procurement-dashboard")
        resp = client.get(url)
        assert resp.status_code == 200
        ctx = resp.context
        assert ctx["total_purchase_orders"] == PurchaseOrder.objects.count()
        due_qs = PurchaseOrder.objects.filter(due_date__lte=today)
        expected_received = (
            due_qs.annotate(
                total_lines=Count("purchase_order_lines"),
                complete_lines=Count(
                    "purchase_order_lines",
                    filter=Q(purchase_order_lines__complete=True),
                ),
            )
            .filter(total_lines__gt=0, total_lines=F("complete_lines"))
            .count()
        )
        assert ctx["orders_received"] == expected_received
        expected_open = (
            due_qs.filter(purchase_order_lines__complete=False).distinct().count()
        )
        assert ctx["pending_receiving"] == expected_open
        assert ctx["total_suppliers"] == Supplier.objects.count()
        content = resp.content.decode()
        assert "POs" in content or "Purchase Orders" in content
        assert "Pending Receiving" in content
        assert "Orders Received" in content
        assert "Suppliers" in content

    def test_supplier_product_ids_api(self, client, supplier, supplier_product):
        """API should return *supplier-product* ids for a given supplier."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        url = reverse("procurement:supplier-product-ids", args=[supplier.pk])
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert "product_ids" in data
        # the returned ids should be the PK of the SupplierProduct itself,
        # since that's what the order line select uses as its option values.
        assert int(supplier_product.pk) in data["product_ids"]
        # pagination assertions for supplier list remain unchanged
        from procurement.models import Supplier

        for i in range(25):
            Supplier.objects.create(name=f"Pagi{i}")
        url = reverse("procurement:supplier-list")
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp.context["page_obj"].paginator is not None
        resp2 = client.get(url + "?page=2")
        assert resp2.status_code == 200


@pytest.mark.django_db
class TestSupplierProduct:
    def test_supplier_product_creation(self, supplier_product):
        assert supplier_product.cost == 10.00

    def test_supplier_product_create_title(self, client, supplier):
        """Form page for a new product shows the "New" heading."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        url = reverse("procurement:supplier-product-create")
        resp = client.get(url)
        assert resp.status_code == 200
        assert "New Supplier Product" in resp.content.decode()

    def test_supplier_product_update_title(self, client, supplier_product):
        """Editing an existing product uses the \"Edit\" heading."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        url = reverse("procurement:supplier-product-update", args=[supplier_product.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        assert "Edit Supplier Product" in resp.content.decode()

    def test_on_purchase_order(self, supplier_product, purchase_order_line):
        assert supplier_product.on_purchase_order() == 5

    def test_receive_view_marks_lines(self, client, purchase_order_line):
        """Submitting receive form should mark line complete and redirect.

        If the received quantity equals the ordered quantity we still
        expect the line to be completed and inventory to be updated by
        that amount.  The parent order's *updated_at* timestamp should
        also be modified.
        """

        from django.contrib.auth.models import User
        from django.urls import reverse

        from inventory.models import Inventory, InventoryLedger

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        po = purchase_order_line.purchase_order
        original = po.updated_at
        url = reverse("procurement:purchase-order-receive", args=[po.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        # page should include header for the received quantity column
        content = resp.content.decode()
        assert "Quantity Received" in content
        # receive-all button should have confirmation JS
        assert "receive_all" in content
        assert (
            "confirm('Are you sure you want to receive ALL remaining quantities?')"
            in content
        )
        # since nothing has been received yet max should equal ordered
        assert f'max="{purchase_order_line.quantity}"' in content
        # we don't need any JS on the receive page; it simply lists
        # the lines and presents inputs for received quantities.
        data = {f"received_{purchase_order_line.id}": purchase_order_line.quantity}
        resp2 = client.post(url, data)
        assert resp2.status_code == 302
        assert resp2.url == reverse("procurement:purchase-order-list")
        purchase_order_line.refresh_from_db()
        assert purchase_order_line.complete is True
        assert purchase_order_line.quantity_received == purchase_order_line.quantity
        # value should reflect the whole line, not just the amount blurred
        assert (
            purchase_order_line.value
            == purchase_order_line.unit_price * purchase_order_line.quantity
        )
        # order timestamp should have moved forward
        po.refresh_from_db()
        assert po.updated_at > original
        # total_amount should stay equal to quantity×unit_price regardless
        # of the line's stored value or received count
        assert (
            po.total_amount
            == purchase_order_line.unit_price * purchase_order_line.quantity
        )
        # after the POST the receiving page should now reflect the received amount
        resp3 = client.get(url)
        assert str(purchase_order_line.quantity_received) in resp3.content.decode()
        # inventory should have been incremented by the same amount
        inv = Inventory.objects.get(product=purchase_order_line.product.product)
        assert inv.quantity == purchase_order_line.quantity
        ledger = (
            InventoryLedger.objects.filter(product=purchase_order_line.product.product)
            .order_by("pk")
            .last()
        )
        assert ledger.quantity == purchase_order_line.quantity

    def test_receive_view_partial_quantity(self, client, purchase_order_line):
        """Receiving less than ordered still updates inventory and keeps line open."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        from inventory.models import Inventory, InventoryLedger

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        po = purchase_order_line.purchase_order
        url = reverse("procurement:purchase-order-receive", args=[po.pk])
        # receive only part of the quantity
        partial = purchase_order_line.quantity - 1
        data = {f"received_{purchase_order_line.id}": partial}
        resp = client.post(url, data)
        assert resp.status_code == 302
        purchase_order_line.refresh_from_db()
        # line should not yet be marked complete or closed
        assert purchase_order_line.complete is False
        assert purchase_order_line.closed is False
        assert purchase_order_line.quantity_received == partial
        # value should not have been touched by a partial receive
        assert purchase_order_line.value is None
        # total_amount must still equal full original cost
        po.refresh_from_db()
        assert (
            po.total_amount
            == purchase_order_line.unit_price * purchase_order_line.quantity
        )
        # after the partial post, max input should be remaining quantity
        resp2 = client.get(url)
        remaining = purchase_order_line.quantity - partial
        assert f'max="{remaining}"' in resp2.content.decode()
        # inventory increased by the partial amount
        inv = Inventory.objects.get(product=purchase_order_line.product.product)
        assert inv.quantity == partial
        ledger = (
            InventoryLedger.objects.filter(product=purchase_order_line.product.product)
            .order_by("pk")
            .last()
        )
        assert ledger.quantity == partial

    def test_receiving_list_pagination(self, client, supplier, supplier_product):
        """The receiving list view should paginate when many orders exist."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)
        # create 12 purchase orders with incomplete lines
        for _ in range(12):
            po = PurchaseOrder.objects.create(supplier=supplier)
            PurchaseOrderLine.objects.create(
                purchase_order=po, product=supplier_product, quantity=2
            )
        # receiving list view removed – regular purchase order list
        # handles pagination.  simply assert the PO list works instead.
        url = reverse("procurement:purchase-order-list")
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp.context["purchase_orders"].paginator is not None
        resp2 = client.get(url + "?page=2")
        assert resp2.status_code == 200

    def test_receiving_list_search(self, client, supplier, supplier_product):
        """Search box should filter receiving orders by supplier or ID."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        from procurement.models import Supplier

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        other = Supplier.objects.create(name="Other Supplier")
        # create one incomplete order for each supplier
        po1 = PurchaseOrder.objects.create(supplier=supplier)
        PurchaseOrderLine.objects.create(
            purchase_order=po1, product=supplier_product, quantity=1
        )
        po2 = PurchaseOrder.objects.create(supplier=other)
        PurchaseOrderLine.objects.create(
            purchase_order=po2, product=supplier_product, quantity=1
        )
        url = reverse("procurement:purchase-order-list")
        # filter by supplier name
        resp = client.get(url, {"q": "Test Supplier"})
        content = resp.content.decode()
        assert po1.order_number in content
        assert "Other Supplier" not in content
        # numeric id search should still work
        resp2 = client.get(url, {"q": str(po2.pk)})
        assert po2.order_number in resp2.content.decode()

    def test_receive_all_button(self, client, supplier, supplier_product):
        """Clicking receive-all should mark every line as received."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        from inventory.models import Inventory, InventoryLedger

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        po = PurchaseOrder.objects.create(supplier=supplier)
        # two lines with different quantities
        line1 = PurchaseOrderLine.objects.create(
            purchase_order=po, product=supplier_product, quantity=3
        )
        line2 = PurchaseOrderLine.objects.create(
            purchase_order=po, product=supplier_product, quantity=5
        )
        url = reverse("procurement:purchase-order-receive", args=[po.pk])
        resp = client.post(url, {"receive_all": "1"})
        assert resp.status_code == 302
        line1.refresh_from_db()
        line2.refresh_from_db()
        assert line1.quantity_received == 3
        assert line2.quantity_received == 5
        assert line1.complete
        assert line2.complete
        # inventory increments by the sum
        inv = Inventory.objects.get(product=supplier_product.product)
        assert inv.quantity == 8
        ledger = (
            InventoryLedger.objects.filter(product=supplier_product.product)
            .order_by("pk")
            .last()
        )
        assert ledger.quantity == 5 or ledger.quantity == 3
        # page should reflect zero remaining on success GET
        getresp = client.get(url)
        assert 'max="0"' in getresp.content.decode()

    def test_receive_refreshes_required_cache(self, client, purchase_order_line):
        """Receiving stock should update required_cached so the low stock list stays accurate."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        from inventory.models import Inventory, ProductionAllocated

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        product = purchase_order_line.product.product
        inv = Inventory.objects.get(product=product)
        # simulate: stock is 0, allocation equals order quantity → item appears needed
        inv.quantity = 0
        inv.save(update_fields=["quantity"])
        pa = ProductionAllocated.objects.get(product=product)
        pa.quantity = purchase_order_line.quantity
        pa.save()
        inv.refresh_from_db()
        assert inv.required_cached == purchase_order_line.quantity

        po = purchase_order_line.purchase_order
        url = reverse("procurement:purchase-order-receive", args=[po.pk])
        client.post(url, {"receive_all": "1"})

        inv.refresh_from_db()
        # after receiving, stock covers the allocation so required_cached must be 0
        assert inv.required_cached == 0


@pytest.mark.django_db
class TestPurchaseOrder:
    def test_purchase_order_creation(self, purchase_order):
        assert purchase_order.supplier.name == "Test Supplier"

    def test_purchase_order_list_pagination(self, client, purchase_order):
        """List view should paginate when many orders exist."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        from procurement.models import PurchaseOrder

        user = User.objects.create_user(username="tester")
        client.force_login(user)
        # create extra orders to force multiple pages
        for i in range(12):
            PurchaseOrder.objects.create(supplier=purchase_order.supplier)
        url = reverse("procurement:purchase-order-list")
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp.context["purchase_orders"].paginator is not None
        resp2 = client.get(url + "?page=2")
        assert resp2.status_code == 200

    def test_purchase_order_list_search(self, client, supplier, purchase_order):
        """Orders should be searchable by supplier name or ID."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        from procurement.models import PurchaseOrder, Supplier

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        other = Supplier.objects.create(name="Other Supplier")
        PurchaseOrder.objects.create(supplier=other)
        url = reverse("procurement:purchase-order-list")
        # search by supplier name
        resp = client.get(url, {"q": "Test Supplier", "status": ""})
        content = resp.content.decode()
        assert purchase_order.supplier.name in content
        assert "Other Supplier" not in content
        # search by numeric ID should still work
        resp2 = client.get(url, {"q": str(purchase_order.pk), "status": ""})
        assert purchase_order.order_number in resp2.content.decode()

    def test_purchase_order_list_filter_received(
        self, client, supplier, supplier_product
    ):
        """Filter=received should show only fully received purchase orders."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        from procurement.models import PurchaseOrder, PurchaseOrderLine

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        received_po = PurchaseOrder.objects.create(supplier=supplier)
        PurchaseOrderLine.objects.create(
            purchase_order=received_po,
            product=supplier_product,
            quantity=1,
            quantity_received=1,
            complete=True,
        )
        open_po = PurchaseOrder.objects.create(supplier=supplier)
        PurchaseOrderLine.objects.create(
            purchase_order=open_po,
            product=supplier_product,
            quantity=1,
            complete=False,
        )

        url = reverse("procurement:purchase-order-list")
        resp = client.get(url, {"filter": "received", "status": ""})
        assert resp.status_code == 200
        content = resp.content.decode()
        assert received_po.order_number in content
        assert open_po.order_number not in content

    def test_purchase_order_list_filter_pending_receiving(
        self, client, supplier, supplier_product
    ):
        """Filter=pending_receiving should show orders with open lines."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        from procurement.models import PurchaseOrder, PurchaseOrderLine

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        open_po = PurchaseOrder.objects.create(supplier=supplier)
        PurchaseOrderLine.objects.create(
            purchase_order=open_po,
            product=supplier_product,
            quantity=2,
            complete=False,
        )
        received_po = PurchaseOrder.objects.create(supplier=supplier)
        PurchaseOrderLine.objects.create(
            purchase_order=received_po,
            product=supplier_product,
            quantity=1,
            quantity_received=1,
            complete=True,
        )

        url = reverse("procurement:purchase-order-list")
        resp = client.get(url, {"filter": "pending_receiving"})
        assert resp.status_code == 200
        content = resp.content.decode()
        assert open_po.order_number in content
        assert received_po.order_number not in content

    def test_purchase_order_properties(self, purchase_order, purchase_order_line):
        # Ensure computed fields work
        assert purchase_order.order_number.startswith("PO")
        assert purchase_order.date == purchase_order.created_at
        assert purchase_order.status == "Open"
        # total amount should always compute from quantity × unit price
        expected = purchase_order_line.product.cost * purchase_order_line.quantity
        from decimal import ROUND_HALF_UP, Decimal

        expected = Decimal(expected).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert purchase_order.total_amount == expected
        # closing the line sets its stored `value` but order total remains
        purchase_order_line.complete = True
        purchase_order_line.save()
        assert purchase_order.status == "Closed"
        assert purchase_order.total_amount == expected

    def test_remaining_and_order_values(self, purchase_order_line):
        """Computed totals should include remaining and received amounts."""
        po = purchase_order_line.purchase_order
        # initially nothing received – order remaining should equal total
        assert po.remaining_total == po.total_amount
        original_total = po.total_amount
        # check line helpers
        assert purchase_order_line.received_total == 0
        assert (
            purchase_order_line.remaining_total
            == purchase_order_line.unit_price * purchase_order_line.quantity
        )
        # simulate receiving some quantity
        purchase_order_line.quantity_received = 2
        purchase_order_line.save()
        # total order value should not change when we record received amounts
        assert po.total_amount == original_total
        expected_rem = (
            purchase_order_line.quantity - 2
        ) * purchase_order_line.unit_price
        assert purchase_order_line.remaining_total == expected_rem
        # order remaining value updates accordingly
        assert po.remaining_total == expected_rem

    def test_purchase_order_detail_shows_received(self, client, purchase_order_line):
        """Detail page includes received and remaining totals."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        po = purchase_order_line.purchase_order
        # update received on the line to simulate partial receipt
        purchase_order_line.quantity_received = 3
        purchase_order_line.save()
        url = reverse("procurement:purchase-order-detail", args=[po.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert str(purchase_order_line.quantity_received) in content
        # the received_total and remaining_total should appear as numbers
        assert str(purchase_order_line.received_total) in content
        assert str(purchase_order_line.remaining_total) in content

    def test_can_close_order_from_list(self, client, purchase_order_line):
        """The list page exposes a close button and orders close via detail POST."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        from inventory.models import Inventory

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        po = purchase_order_line.purchase_order
        list_url = reverse("procurement:purchase-order-list")
        # list page should render the close button for open orders
        resp = client.get(list_url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert 'name="close_order"' in content

        # perform the close action by posting to the detail endpoint
        detail_url = reverse("procurement:purchase-order-detail", args=[po.pk])
        resp2 = client.post(detail_url, {"close_order": "1"})
        assert resp2.status_code == 302
        assert resp2.url == detail_url
        po.refresh_from_db()
        assert po.status == "Closed"

        # lines should be marked closed but inventory unaffected
        for line in po.purchase_order_lines.all():
            assert line.complete is True
            assert line.closed is True
            assert line.quantity_received == 0
            assert line.value is None
        inv = Inventory.objects.filter(
            product=purchase_order_line.product.product
        ).first()
        assert inv is None or inv.quantity == 0

        # list page no longer renders a close button for the closed order
        resp3 = client.get(list_url)
        assert 'name="close_order"' not in resp3.content.decode()
        # detail page likewise no longer contains close controls
        resp4 = client.get(detail_url)
        assert 'name="close_order"' not in resp4.content.decode()

    def test_create_view_prefills_and_filters(self, client, supplier, supplier_product):
        """GET should prefill supplier and limit the product choices on each line."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        url = reverse("procurement:purchase-order-create") + f"?supplier={supplier.pk}"
        response = client.get(url)
        assert response.status_code == 200
        form = response.context["form"]
        # initial supplier should be set (string representation is fine)
        assert str(form.initial.get("supplier")) == str(supplier.pk)
        from django import forms

        assert isinstance(form.fields["supplier"].widget, forms.HiddenInput)
        # formset shouldn't expose a complete field but should allow deletion
        fs = response.context["lines_formset"]
        for f in fs:
            assert "complete" not in f.fields
            assert "DELETE" in f.fields
            qs = f.fields["product"].queryset
            assert list(qs) == list(supplier.supplier_products.all())

    def test_supplier_product_create_prefills_supplier(self, client, supplier, product):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        url = (
            reverse("procurement:supplier-product-create") + f"?supplier={supplier.pk}"
        )
        response = client.get(url)
        assert response.status_code == 200
        form = response.context["form"]
        assert str(form.initial.get("supplier")) == str(supplier.pk)
        from django import forms

        assert isinstance(form.fields["supplier"].widget, forms.HiddenInput)

        # after POST we should end up back at the supplier detail page
        post_url = reverse("procurement:supplier-product-create")
        data = {"supplier": supplier.pk, "product": product.pk, "cost": "5.00"}
        resp2 = client.post(post_url, data)
        assert resp2.status_code == 302
        assert resp2.url == reverse("procurement:supplier-detail", args=[supplier.pk])

    def test_purchase_order_form_js_syntax(self, client, supplier):
        """Ensure the order_form.js static file compiles and is referenced."""
        import subprocess
        from pathlib import Path

        from django.conf import settings
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="js2")
        client.force_login(user)
        url = reverse("procurement:purchase-order-create")
        resp = client.get(url)
        assert resp.status_code == 200
        html = resp.content.decode()
        assert "order_form.js" in html
        js_path = Path(settings.BASE_DIR) / "static" / "js" / "order_form.js"
        result = subprocess.run(
            ["node", "--check", str(js_path)], capture_output=True, text=True
        )
        assert result.returncode == 0, f"JS syntax error: {result.stderr}"

    def test_create_view_auto_supplier_and_lines(
        self, client, supplier, supplier_product
    ):
        """The create view should prefill supplier from the query string and
        allow submitting one or more order lines.  Deletion checkboxes should
        be rendered but can be ignored on creation."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        url = reverse("procurement:purchase-order-create") + f"?supplier={supplier.pk}"
        # build post data for a single line using the actual prefix
        prefix = "purchase_order_lines"
        data = {
            "supplier": supplier.pk,
            f"{prefix}-TOTAL_FORMS": "2",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
            f"{prefix}-0-product": supplier_product.pk,
            f"{prefix}-0-quantity": "3",
            f"{prefix}-1-product": supplier_product.pk,
            f"{prefix}-1-quantity": "4",
        }
        response = client.post(url, data)
        assert response.status_code == 302
        po = PurchaseOrder.objects.latest("pk")
        assert po.supplier == supplier
        lines = po.purchase_order_lines.all()
        # we posted two lines so both should exist
        assert lines.count() == 2
        first, second = lines.order_by("pk")
        assert first.product == supplier_product
        assert first.quantity == 3
        assert second.product == supplier_product
        assert second.quantity == 4

    def test_create_view_rejects_mismatched_product(
        self, client, supplier, supplier_product, product
    ):
        """POSTing a supplier-product that doesn't belong to the chosen
        supplier should result in form errors and not create a PO."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        from procurement.models import Supplier, SupplierProduct

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        # create a second supplier and a product relationship pointing at it
        other_supplier = Supplier.objects.create(name="OtherSup")
        other_sp = SupplierProduct.objects.create(
            supplier=other_supplier,
            product=product,
            cost=7.00,
        )
        url = reverse("procurement:purchase-order-create") + f"?supplier={supplier.pk}"
        prefix = "purchase_order_lines"
        data = {
            "supplier": supplier.pk,
            f"{prefix}-TOTAL_FORMS": "1",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
            # deliberately supply the other supplier's product id
            f"{prefix}-0-product": other_sp.pk,
            f"{prefix}-0-quantity": "5",
        }
        response = client.post(url, data)
        # should re-render with errors rather than redirect
        assert response.status_code == 200
        fs = response.context["lines_formset"]
        assert not fs.is_valid()
        # no purchase order should have been created
        assert not PurchaseOrder.objects.filter(supplier=supplier).exists()

    def test_create_view_rejects_empty_order(self, client, supplier):
        """Submitting a purchase order with no line items should fail validation."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        url = reverse("procurement:purchase-order-create") + f"?supplier={supplier.pk}"
        prefix = "purchase_order_lines"
        data = {
            "supplier": supplier.pk,
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
        assert (
            "A purchase order must have at least one line item." in fs.non_form_errors()
        )
        assert not PurchaseOrder.objects.filter(supplier=supplier).exists()


@pytest.mark.django_db
class TestPurchaseOrderLine:
    def test_purchase_order_line_creation(self, purchase_order_line):
        assert purchase_order_line.quantity == 5

    def test_purchase_order_line_receive(self, purchase_order_line):
        from procurement.services import receive_purchase_order_line

        inventory = Inventory.objects.get(product=purchase_order_line.product.product)
        receive_purchase_order_line(purchase_order_line, purchase_order_line.quantity)
        inventory.refresh_from_db()
        assert inventory.quantity == 5
        ledger = (
            InventoryLedger.objects.filter(product=purchase_order_line.product.product)
            .order_by("pk")
            .first()
        )
        assert ledger is not None
        assert ledger.quantity == 5
        purchase_ledger = PurchaseLedger.objects.filter(
            transaction_id=purchase_order_line.purchase_order.pk
        ).first()
        assert purchase_ledger is not None
        assert purchase_ledger.quantity == 5
        purchase_order_line.refresh_from_db()
        assert purchase_order_line.complete is True
        assert purchase_order_line.closed is True


@pytest.mark.django_db
class TestStoreConfirmation:
    """Tests for the scan-to-store confirmation workflow."""

    def test_store_confirm_get(self, client, purchase_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        po = purchase_order_line.purchase_order
        url = reverse("procurement:store-confirm", args=[po.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Store Confirmation" in content
        assert "0 / 1 confirmed" in content

    def test_store_confirm_manual_line(self, client, purchase_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        po = purchase_order_line.purchase_order
        url = reverse("procurement:store-confirm", args=[po.pk])
        resp = client.post(
            url,
            {"line_id": str(purchase_order_line.pk)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["line_id"] == purchase_order_line.pk
        assert data["all_confirmed"] is True

        purchase_order_line.refresh_from_db()
        assert purchase_order_line.store_confirmed is True
        assert purchase_order_line.store_confirmed_at is not None

    def test_store_confirm_scan_barcode(self, client, purchase_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        product = purchase_order_line.product.product
        product.barcode = "STORE-BC-123"
        product.save(update_fields=["barcode"])

        po = purchase_order_line.purchase_order
        url = reverse("procurement:store-confirm", args=[po.pk])
        resp = client.post(
            url,
            {"scan_value": "STORE-BC-123"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["product_name"] == product.name

        purchase_order_line.refresh_from_db()
        assert purchase_order_line.store_confirmed is True

    def test_store_confirm_scan_sku(self, client, purchase_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        product = purchase_order_line.product.product
        product.sku = "STORE-SKU-999"
        product.save(update_fields=["sku"])

        po = purchase_order_line.purchase_order
        url = reverse("procurement:store-confirm", args=[po.pk])
        resp = client.post(
            url,
            {"scan_value": "STORE-SKU-999"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        purchase_order_line.refresh_from_db()
        assert purchase_order_line.store_confirmed is True

    def test_store_confirm_scan_no_match(self, client, purchase_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        po = purchase_order_line.purchase_order
        url = reverse("procurement:store-confirm", args=[po.pk])
        resp = client.post(
            url,
            {"scan_value": "UNKNOWN-CODE"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "No product matches" in data["error"]

    def test_store_confirm_scan_already_confirmed(self, client, purchase_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        product = purchase_order_line.product.product
        product.barcode = "STORE-BC-DONE"
        product.save(update_fields=["barcode"])

        purchase_order_line.store_confirmed = True
        purchase_order_line.save(update_fields=["store_confirmed"])

        po = purchase_order_line.purchase_order
        url = reverse("procurement:store-confirm", args=[po.pk])
        resp = client.post(
            url,
            {"scan_value": "STORE-BC-DONE"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        data = resp.json()
        assert data["ok"] is False
        assert "no unconfirmed lines" in data["error"].lower()

    def test_store_confirm_invalid_line_id(self, client, purchase_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        po = purchase_order_line.purchase_order
        url = reverse("procurement:store-confirm", args=[po.pk])
        resp = client.post(
            url,
            {"line_id": "99999"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        data = resp.json()
        assert data["ok"] is False
        assert "not found" in data["error"].lower()

    def test_store_confirm_reset(self, client, purchase_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        purchase_order_line.store_confirmed = True
        purchase_order_line.save(update_fields=["store_confirmed"])

        po = purchase_order_line.purchase_order
        url = reverse("procurement:store-confirm-reset", args=[po.pk])
        resp = client.post(url)
        assert resp.status_code == 302

        purchase_order_line.refresh_from_db()
        assert purchase_order_line.store_confirmed is False

    def test_all_store_confirmed_property(self, purchase_order_line):
        po = purchase_order_line.purchase_order
        assert po.all_store_confirmed is False

        purchase_order_line.store_confirmed = True
        purchase_order_line.save(update_fields=["store_confirmed"])
        assert po.all_store_confirmed is True

    def test_store_confirm_non_ajax_redirect(self, client, purchase_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        po = purchase_order_line.purchase_order
        url = reverse("procurement:store-confirm", args=[po.pk])
        # POST without AJAX header should redirect
        resp = client.post(url, {"line_id": str(purchase_order_line.pk)})
        assert resp.status_code == 302

    def test_store_confirm_requires_login(self, client, purchase_order_line):
        from django.urls import reverse

        po = purchase_order_line.purchase_order
        url = reverse("procurement:store-confirm", args=[po.pk])
        resp = client.get(url)
        assert resp.status_code == 302
        assert "/login/" in resp.url or "/accounts/login/" in resp.url

    def test_po_detail_has_scan_to_store_link(self, client, purchase_order_line):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        po = purchase_order_line.purchase_order
        url = reverse("procurement:purchase-order-detail", args=[po.pk])
        resp = client.get(url)
        content = resp.content.decode()
        confirm_url = reverse("procurement:store-confirm", args=[po.pk])
        assert confirm_url in content
        assert "Scan to Store" in content
