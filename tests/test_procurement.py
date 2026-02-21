import pytest
from procurement.models import PurchaseLedger, PurchaseOrder
from inventory.models import Inventory, InventoryLedger


@pytest.mark.django_db
class TestSupplier:
    def test_supplier_creation(self, supplier):
        assert supplier.name == "Test Supplier"

    def test_supplier_contact_creation(self, supplier_contact):
        assert supplier_contact.name == "Test Contact"

    def test_supplier_detail_context(self, client, supplier, supplier_product):
        from django.urls import reverse

        url = reverse("procurement:supplier-detail", args=[supplier.pk])
        response = client.get(url)
        assert response.status_code == 200
        # supplier_products is now a page object
        products_page = response.context.get("supplier_products")
        assert products_page is not None
        assert supplier_product in products_page.object_list
        # purchase_orders also should be a page object, initially empty
        assert "purchase_orders" in response.context
        purchase_page = response.context.get("purchase_orders")
        assert hasattr(purchase_page, "paginator")
        # see all links present in rendered content
        content = response.content.decode()
        assert f"href=\"{reverse('procurement:supplier-purchaseorders', args=[supplier.pk])}\"" in content
        assert f"href=\"{reverse('procurement:supplier-products', args=[supplier.pk])}\"" in content

@pytest.mark.django_db
class TestSupplierProduct:
    def test_supplier_product_creation(self, supplier_product):
        assert supplier_product.cost == 10.00

    def test_on_purchase_order(self, supplier_product, purchase_order_line):
        assert supplier_product.on_purchase_order() == 5

    def test_receive_view_marks_lines(self, client, purchase_order_line):
        """Submitting receive form should mark line complete and redirect.

        If the received quantity equals the ordered quantity we still
        expect the line to be completed and inventory to be updated by
        that amount.
        """
        from django.urls import reverse
        from inventory.models import Inventory, InventoryLedger

        po = purchase_order_line.purchase_order
        url = reverse("procurement:purchase-order-receive", args=[po.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        # page should include header for already received quantity
        content = resp.content.decode()
        assert "Already Received" in content
        # since nothing has been received yet max should equal ordered
        assert f"max=\"{purchase_order_line.quantity}\"" in content
        data = {f"received_{purchase_order_line.id}": purchase_order_line.quantity}
        resp2 = client.post(url, data)
        assert resp2.status_code == 302
        assert resp2.url == reverse("procurement:purchase-order-detail", args=[po.pk])
        purchase_order_line.refresh_from_db()
        assert purchase_order_line.complete is True
        assert purchase_order_line.quantity_received == purchase_order_line.quantity
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
        """Receiving less than ordered still updates inventory and closes line."""
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

@pytest.mark.django_db
class TestPurchaseOrder:
    def test_purchase_order_creation(self, purchase_order):
        assert purchase_order.supplier.name == "Test Supplier"

    def test_purchase_order_properties(self, purchase_order, purchase_order_line):
        # Ensure computed fields work
        assert purchase_order.order_number.startswith("PO")
        assert purchase_order.date == purchase_order.created_at
        assert purchase_order.status == "Open"
        # total amount should calculate even before completion and use two decimals
        expected = purchase_order_line.product.cost * purchase_order_line.quantity
        from decimal import Decimal, ROUND_HALF_UP
        expected = Decimal(expected).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert purchase_order.total_amount == expected
        # close the line and recalc
        purchase_order_line.complete = True
        purchase_order_line.save()
        assert purchase_order.status == "Closed"
        # total amount should equal line value now that value field populated
        total = purchase_order.purchase_order_lines.aggregate(total=__import__('django').db.models.Sum('value'))['total']
        assert purchase_order.total_amount == (total or 0)

    def test_purchase_order_detail_shows_received(self, client, purchase_order_line):
        """Detail page includes quantity_received column."""
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