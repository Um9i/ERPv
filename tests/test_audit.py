"""Tests for audit trail fields and field-level change tracking."""

from decimal import Decimal

import pytest

from main.models import AuditLog

pytestmark = pytest.mark.integration


@pytest.mark.django_db
class TestAuditTrailFields:
    """Verify created_by / updated_by are populated on creation."""

    def test_purchase_order_created_by(self, client, supplier, supplier_product):
        from django.contrib.auth.models import User
        from django.urls import reverse

        from procurement.models import PurchaseOrder

        user = User.objects.create_user(username="auditor")
        client.force_login(user)

        url = reverse("procurement:purchase-order-create") + f"?supplier={supplier.pk}"
        prefix = "purchase_order_lines"
        data = {
            "supplier": supplier.pk,
            f"{prefix}-TOTAL_FORMS": "1",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
            f"{prefix}-0-product": supplier_product.pk,
            f"{prefix}-0-quantity": "5",
        }
        response = client.post(url, data)
        assert response.status_code == 302
        po = PurchaseOrder.objects.latest("pk")
        assert po.created_by == user
        assert po.updated_by == user

    def test_sales_order_created_by(self, client, customer, customer_product):
        from django.contrib.auth.models import User
        from django.urls import reverse

        from sales.models import SalesOrder

        user = User.objects.create_user(username="auditor")
        client.force_login(user)

        url = reverse("sales:sales-order-create") + f"?customer={customer.pk}"
        prefix = "sales_order_lines"
        data = {
            "customer": customer.pk,
            f"{prefix}-TOTAL_FORMS": "1",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
            f"{prefix}-0-product": customer_product.pk,
            f"{prefix}-0-quantity": "3",
        }
        response = client.post(url, data)
        assert response.status_code == 302
        so = SalesOrder.objects.latest("pk")
        assert so.created_by == user
        assert so.updated_by == user

    def test_inventory_adjust_created_by(self, client, product):
        from django.contrib.auth.models import User
        from django.urls import reverse

        from inventory.models import Inventory, InventoryAdjust

        user = User.objects.create_user(username="auditor")
        client.force_login(user)

        inventory = Inventory.objects.get(product=product)
        url = reverse("inventory:inventory-adjust", args=[inventory.pk])
        response = client.post(url, {"quantity": 10})
        assert response.status_code == 302
        adj = InventoryAdjust.objects.filter(product=product).latest("pk")
        assert adj.created_by == user
        assert adj.updated_by == user

    def test_stock_transfer_created_by(self, client, product):
        from django.contrib.auth.models import User
        from django.urls import reverse

        from inventory.models import (
            Inventory,
            InventoryLocation,
            Location,
            StockTransfer,
        )

        user = User.objects.create_user(username="auditor")
        client.force_login(user)

        inv = Inventory.objects.get(product=product)
        inv.quantity = 50
        inv.save(update_fields=["quantity"])
        bin_a = Location.objects.create(name="Audit Bin A")
        bin_b = Location.objects.create(name="Audit Bin B")
        InventoryLocation.objects.create(inventory=inv, location=bin_a, quantity=50)

        url = reverse("inventory:stock-transfer", args=[inv.pk])
        response = client.post(
            url,
            {
                "from_location": bin_a.pk,
                "to_location": bin_b.pk,
                "quantity": 10,
                "note": "audit test",
            },
        )
        assert response.status_code == 302
        transfer = StockTransfer.objects.latest("pk")
        assert transfer.created_by == user
        assert transfer.updated_by == user

    def test_production_job_created_by(self, client, bom):
        from django.contrib.auth.models import User
        from django.urls import reverse

        from production.models import Production

        user = User.objects.create_user(username="auditor")
        client.force_login(user)

        url = reverse("production:production-create")
        response = client.post(
            url,
            {"product": bom.product.pk, "quantity": 10},
        )
        assert response.status_code == 302
        job = Production.objects.latest("pk")
        assert job.created_by == user
        assert job.updated_by == user


@pytest.mark.django_db
class TestFieldLevelChangeTracking:
    """Verify AuditLog entries are created when critical fields change."""

    def test_supplier_product_cost_change_logged(
        self, client, supplier, supplier_product
    ):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="pricer")
        client.force_login(user)

        old_cost = supplier_product.cost
        url = reverse("procurement:supplier-product-update", args=[supplier_product.pk])
        response = client.post(
            url,
            {
                "supplier": supplier.pk,
                "product": supplier_product.product.pk,
                "cost": "15.00",
            },
        )
        assert response.status_code == 302
        supplier_product.refresh_from_db()
        assert supplier_product.cost == 15

        log = AuditLog.objects.filter(
            object_id=supplier_product.pk, field_name="cost"
        ).first()
        assert log is not None
        assert Decimal(log.old_value) == old_cost
        assert Decimal(log.new_value) == Decimal("15.00")
        assert log.changed_by == user

    def test_customer_product_price_change_logged(
        self, client, customer, customer_product
    ):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="pricer")
        client.force_login(user)

        old_price = customer_product.price
        url = reverse("sales:customer-product-update", args=[customer_product.pk])
        response = client.post(
            url,
            {
                "customer": customer.pk,
                "product": customer_product.product.pk,
                "price": "25.00",
            },
        )
        assert response.status_code == 302
        customer_product.refresh_from_db()
        assert customer_product.price == 25

        log = AuditLog.objects.filter(
            object_id=customer_product.pk, field_name="price"
        ).first()
        assert log is not None
        assert Decimal(log.old_value) == old_price
        assert Decimal(log.new_value) == Decimal("25.00")
        assert log.changed_by == user

    def test_no_log_when_value_unchanged(self, client, supplier, supplier_product):
        from django.contrib.auth.models import User
        from django.urls import reverse

        user = User.objects.create_user(username="pricer")
        client.force_login(user)

        url = reverse("procurement:supplier-product-update", args=[supplier_product.pk])
        # submit the same cost value
        response = client.post(
            url,
            {
                "supplier": supplier.pk,
                "product": supplier_product.product.pk,
                "cost": str(supplier_product.cost),
            },
        )
        assert response.status_code == 302
        assert not AuditLog.objects.filter(
            object_id=supplier_product.pk, field_name="cost"
        ).exists()
