import pytest
from procurement.models import PurchaseLedger, PurchaseOrder, PurchaseOrderLine
from inventory.models import Inventory, InventoryLedger


@pytest.mark.django_db
class TestSupplier:
    def test_supplier_creation(self, supplier):
        assert supplier.name == "Test Supplier"

    def test_supplier_contact_creation(self, supplier_contact):
        assert supplier_contact.name == "Test Contact"

    def test_supplier_detail_context(self, client, supplier, supplier_product):
        from django.urls import reverse
        from procurement.models import PurchaseOrder

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
        assert f"href=\"{reverse('procurement:supplier-purchaseorders', args=[supplier.pk])}\"" in content
        assert f"href=\"{reverse('procurement:supplier-products', args=[supplier.pk])}\"" in content

    def test_supplier_list_pagination(self, client, supplier):
        """Supplier list should paginate when many entries exist."""
        from django.urls import reverse
        from procurement.models import Supplier
        # create enough extra suppliers to require more than one page
        for i in range(12):
            Supplier.objects.create(name=f"Pagi{i}")
        url = reverse("procurement:supplier-list")
        resp = client.get(url)
        assert resp.status_code == 200
        # paginator exists regardless of page count
        assert resp.context["suppliers"].paginator is not None
        resp2 = client.get(url + "?page=2")
        assert resp2.status_code == 200

    def test_supplier_list_search(self, client, supplier):
        """Search box should filter suppliers by name."""
        from django.urls import reverse
        from procurement.models import Supplier

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

    def test_dashboard_metrics(self, client, supplier, purchase_order, purchase_order_line):
        from django.urls import reverse
        from django.contrib.auth.models import User
        from procurement.models import PurchaseOrder, PurchaseOrderLine, Supplier

        user = User.objects.create_user(username="dashuser")
        client.force_login(user)
        url = reverse("procurement:procurement-dashboard")
        resp = client.get(url)
        assert resp.status_code == 200
        ctx = resp.context
        assert ctx["total_purchase_orders"] == PurchaseOrder.objects.count()
        assert ctx["pending_receiving"] == PurchaseOrderLine.objects.filter(complete=False).count()
        assert ctx["total_suppliers"] == Supplier.objects.count()
        content = resp.content.decode()
        assert "POs" in content or "Purchase Orders" in content
        assert "Pending Receiving" in content
        assert "Suppliers" in content

    def test_supplier_product_ids_api(self, client, supplier, supplier_product):
        """API should return *supplier-product* ids for a given supplier."""
        from django.urls import reverse
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
        for i in range(12):
            Supplier.objects.create(name=f"Pagi{i}")
        url = reverse("procurement:supplier-list")
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp.context["suppliers"].paginator is not None
        resp2 = client.get(url + "?page=2")
        assert resp2.status_code == 200

@pytest.mark.django_db
class TestSupplierProduct:
    def test_supplier_product_creation(self, supplier_product):
        assert supplier_product.cost == 10.00

    def test_supplier_product_create_title(self, client, supplier):
        """Form page for a new product shows the "New" heading."""
        from django.urls import reverse
        url = reverse("procurement:supplier-product-create")
        resp = client.get(url)
        assert resp.status_code == 200
        assert "<h1>New Supplier Product</h1>" in resp.content.decode()

    def test_supplier_product_update_title(self, client, supplier_product):
        """Editing an existing product uses the "Edit" heading."""
        from django.urls import reverse
        url = reverse("procurement:supplier-product-update", args=[supplier_product.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        assert "<h1>Edit Supplier Product</h1>" in resp.content.decode()

    def test_on_purchase_order(self, supplier_product, purchase_order_line):
        assert supplier_product.on_purchase_order() == 5

    def test_receive_view_marks_lines(self, client, purchase_order_line):
        """Submitting receive form should mark line complete and redirect.

        If the received quantity equals the ordered quantity we still
        expect the line to be completed and inventory to be updated by
        that amount.  The parent order's *updated_at* timestamp should
        also be modified.
        """
        from django.urls import reverse
        from inventory.models import Inventory, InventoryLedger
        import datetime

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
        assert "confirm('Are you sure you want to receive ALL remaining quantities?')" in content
        # since nothing has been received yet max should equal ordered
        assert f"max=\"{purchase_order_line.quantity}\"" in content
        # we don't need any JS on the receive page; it simply lists
        # the lines and presents inputs for received quantities.
        data = {f"received_{purchase_order_line.id}": purchase_order_line.quantity}
        resp2 = client.post(url, data)
        assert resp2.status_code == 302
        assert resp2.url == reverse("procurement:purchase-order-receiving-list")
        purchase_order_line.refresh_from_db()
        assert purchase_order_line.complete is True
        assert purchase_order_line.quantity_received == purchase_order_line.quantity
        # value should reflect the whole line, not just the amount blurred
        assert purchase_order_line.value == purchase_order_line.unit_price * purchase_order_line.quantity
        # order timestamp should have moved forward
        po.refresh_from_db()
        assert po.updated_at > original
        # total_amount should stay equal to quantity×unit_price regardless
        # of the line's stored value or received count
        assert po.total_amount == purchase_order_line.unit_price * purchase_order_line.quantity
        # after the POST the receiving page should now reflect the received amount
        resp3 = client.get(url)
        assert str(purchase_order_line.quantity_received) in resp3.content.decode()
        # inventory should have been incremented by the same amount
        inv = Inventory.objects.get(product=purchase_order_line.product.product)
        assert inv.quantity == purchase_order_line.quantity
        ledger = InventoryLedger.objects.filter(
            product=purchase_order_line.product.product
        ).order_by("pk").last()
        assert ledger.quantity == purchase_order_line.quantity

    def test_receive_view_partial_quantity(self, client, purchase_order_line):
        """Receiving less than ordered still updates inventory and keeps line open."""
        from django.urls import reverse
        from inventory.models import Inventory, InventoryLedger

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
        assert po.total_amount == purchase_order_line.unit_price * purchase_order_line.quantity
        # after the partial post, max input should be remaining quantity
        resp2 = client.get(url)
        remaining = purchase_order_line.quantity - partial
        assert f"max=\"{remaining}\"" in resp2.content.decode()
        # inventory increased by the partial amount
        inv = Inventory.objects.get(product=purchase_order_line.product.product)
        assert inv.quantity == partial
        ledger = InventoryLedger.objects.filter(
            product=purchase_order_line.product.product
        ).order_by("pk").last()
        assert ledger.quantity == partial

    def test_receiving_list_pagination(self, client, supplier, supplier_product):
        """The receiving list view should paginate when many orders exist."""
        from django.urls import reverse
        # create 12 purchase orders with incomplete lines
        for _ in range(12):
            po = PurchaseOrder.objects.create(supplier=supplier)
            PurchaseOrderLine.objects.create(purchase_order=po, product=supplier_product, quantity=2)
        url = reverse("procurement:purchase-order-receiving-list")
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp.context["purchase_orders"].paginator is not None
        resp2 = client.get(url + "?page=2")
        assert resp2.status_code == 200

    def test_receiving_list_search(self, client, supplier, supplier_product):
        """Search box should filter receiving orders by supplier or ID."""
        from django.urls import reverse
        from procurement.models import Supplier
        other = Supplier.objects.create(name="Other Supplier")
        # create one incomplete order for each supplier
        po1 = PurchaseOrder.objects.create(supplier=supplier)
        PurchaseOrderLine.objects.create(purchase_order=po1, product=supplier_product, quantity=1)
        po2 = PurchaseOrder.objects.create(supplier=other)
        PurchaseOrderLine.objects.create(purchase_order=po2, product=supplier_product, quantity=1)
        url = reverse("procurement:purchase-order-receiving-list")
        resp = client.get(url, {"q": "Test Supplier"})
        content = resp.content.decode()
        assert po1.order_number in content
        assert "Other Supplier" not in content
        # numeric id search
        resp2 = client.get(url, {"q": str(po2.pk)})
        assert po2.order_number in resp2.content.decode()

    def test_receive_all_button(self, client, supplier, supplier_product):
        """Clicking receive-all should mark every line as received."""
        from django.urls import reverse
        from inventory.models import Inventory, InventoryLedger

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
        ledger = InventoryLedger.objects.filter(
            product=supplier_product.product
        ).order_by("pk").last()
        assert ledger.quantity == 5 or ledger.quantity == 3
        # page should reflect zero remaining on success GET
        getresp = client.get(url)
        assert "max=\"0\"" in getresp.content.decode()

@pytest.mark.django_db
class TestPurchaseOrder:
    def test_purchase_order_creation(self, purchase_order):
        assert purchase_order.supplier.name == "Test Supplier"

    def test_purchase_order_list_pagination(self, client, purchase_order):
        """List view should paginate when many orders exist."""
        from django.urls import reverse
        from procurement.models import PurchaseOrder
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
        from django.urls import reverse
        from procurement.models import PurchaseOrder, Supplier

        other = Supplier.objects.create(name="Other Supplier")
        PurchaseOrder.objects.create(supplier=other)
        url = reverse("procurement:purchase-order-list")
        # search by supplier name
        resp = client.get(url, {"q": "Test Supplier"})
        content = resp.content.decode()
        assert purchase_order.supplier.name in content
        assert "Other Supplier" not in content
        # search by numeric ID should still work
        resp2 = client.get(url, {"q": str(purchase_order.pk)})
        assert purchase_order.order_number in resp2.content.decode()

    def test_purchase_order_properties(self, purchase_order, purchase_order_line):
        # Ensure computed fields work
        assert purchase_order.order_number.startswith("PO")
        assert purchase_order.date == purchase_order.created_at
        assert purchase_order.status == "Open"
        # total amount should always compute from quantity × unit price
        expected = purchase_order_line.product.cost * purchase_order_line.quantity
        from decimal import Decimal, ROUND_HALF_UP
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
        assert purchase_order_line.remaining_total == purchase_order_line.unit_price * purchase_order_line.quantity
        # simulate receiving some quantity
        purchase_order_line.quantity_received = 2
        purchase_order_line.save()
        # total order value should not change when we record received amounts
        assert po.total_amount == original_total
        expected_rem = (purchase_order_line.quantity - 2) * purchase_order_line.unit_price
        assert purchase_order_line.remaining_total == expected_rem
        # order remaining value updates accordingly
        assert po.remaining_total == expected_rem

    def test_purchase_order_detail_shows_received(self, client, purchase_order_line):
        """Detail page includes received and remaining totals."""
        from django.urls import reverse
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

    def test_can_close_order_from_detail(self, client, purchase_order_line):
        """A button on the detail page allows manual closing of an order."""
        from django.urls import reverse
        from inventory.models import Inventory

        po = purchase_order_line.purchase_order
        url = reverse("procurement:purchase-order-detail", args=[po.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert 'name="close_order"' in content
        # perform the close action
        resp2 = client.post(url, {"close_order": "1"})
        assert resp2.status_code == 302
        assert resp2.url == url
        po.refresh_from_db()
        assert po.status == "Closed"
        # all lines should now be complete/closed but quantities untouched
        for line in po.purchase_order_lines.all():
            assert line.complete is True
            assert line.closed is True
            assert line.quantity_received == 0
            assert line.value is None
        # closing does not alter inventory
        inv = Inventory.objects.filter(product=purchase_order_line.product.product).first()
        assert inv is None or inv.quantity == 0
        # after closing the detail page no longer shows the close button
        resp3 = client.get(url)
        assert 'name="close_order"' not in resp3.content.decode()
        # open order value may still show remaining amount
        assert "Open Order Value" in resp3.content.decode()

    def test_create_view_prefills_and_filters(self, client, supplier, supplier_product):
        """GET should prefill supplier and limit the product choices on each line."""
        from django.urls import reverse

        url = reverse("procurement:purchase-order-create") + f"?supplier={supplier.pk}"
        response = client.get(url)
        assert response.status_code == 200
        form = response.context["form"]
        # initial supplier should be set (string representation is fine)
        assert str(form.initial.get("supplier")) == str(supplier.pk)
        from django import forms
        assert isinstance(form.fields["supplier"].widget, forms.HiddenInput)
        # formset shouldn't expose a complete field or deletion
        fs = response.context["lines_formset"]
        for f in fs:
            assert "complete" not in f.fields
            assert not hasattr(f, "DELETE")
            qs = f.fields["product"].queryset
            assert list(qs) == list(supplier.supplier_products.all())

    def test_supplier_product_create_prefills_supplier(self, client, supplier, product):
        from django.urls import reverse

        url = reverse("procurement:supplier-product-create") + f"?supplier={supplier.pk}"
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

    def test_create_view_auto_supplier_and_lines(self, client, supplier, supplier_product):
        """The create view should prefill supplier from the query string and
        allow submitting one or more order lines."""
        from django.urls import reverse

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
        first, second = lines.order_by('pk')
        assert first.product == supplier_product
        assert first.quantity == 3
        assert second.product == supplier_product
        assert second.quantity == 4

    def test_create_view_rejects_mismatched_product(self, client, supplier, supplier_product, product):
        """POSTing a supplier-product that doesn't belong to the chosen
        supplier should result in form errors and not create a PO."""
        from procurement.models import Supplier, SupplierProduct
        from django.urls import reverse

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

@pytest.mark.django_db
class TestPurchaseOrderLine:
    def test_purchase_order_line_creation(self, purchase_order_line):
        assert purchase_order_line.quantity == 5

    def test_purchase_order_line_save(self, purchase_order_line):
        inventory = Inventory.objects.get(product=purchase_order_line.product.product)
        purchase_order_line.complete = True
        purchase_order_line.save()
        assert inventory.quantity == 0
        ledger = InventoryLedger.objects.filter(product=purchase_order_line.product.product).order_by("pk").first()
        assert ledger is not None
        assert ledger.quantity == 5
        purchase_ledger = PurchaseLedger.objects.filter(transaction_id=purchase_order_line.purchase_order.pk).first()
        assert purchase_ledger is not None
        assert purchase_ledger.quantity == 5