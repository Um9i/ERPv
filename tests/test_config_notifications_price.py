from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse

from config.models import PairedInstance
from inventory.models import Product
from procurement.models import Supplier, SupplierProduct


@pytest.fixture
def staff_user(django_user_model):
    return django_user_model.objects.create_user(username="staff", is_staff=True)


@pytest.fixture
def product():
    return Product.objects.create(
        name="Widget", sale_price=Decimal("10.00"), catalogue_item=True
    )


@pytest.fixture
def paired_with_product(product):
    supplier = Supplier.objects.create(name="Remote Co")
    SupplierProduct.objects.create(
        supplier=supplier, product=product, cost=Decimal("5.00")
    )
    pi = PairedInstance.objects.create(
        name="Remote", url="https://remote.example.com", api_key="theirkey"
    )
    pi.supplier = supplier
    pi.save()
    return pi


@pytest.mark.django_db
def test_price_change_notifies_active_paired_instances(
    client, staff_user, product, paired_with_product
):
    client.force_login(staff_user)
    with (
        patch(
            "inventory.views._notify_remote_customer_product", return_value=True
        ) as mock_notify,
        patch(
            "inventory.views._notify_remote_supplier_product_cost", return_value=True
        ),
    ):
        client.post(
            reverse("inventory:product-update", args=[product.pk]),
            {
                "name": product.name,
                "description": "",
                "sale_price": "15.00",
                "catalogue_item": True,
            },
        )
        mock_notify.assert_called_once_with(
            paired_with_product, "Widget", Decimal("15.00")
        )


@pytest.mark.django_db
def test_no_notification_when_price_unchanged(
    client, staff_user, product, paired_with_product
):
    client.force_login(staff_user)
    with patch(
        "inventory.views._notify_remote_customer_product", return_value=True
    ) as mock_notify:
        client.post(
            reverse("inventory:product-update", args=[product.pk]),
            {
                "name": product.name,
                "description": "",
                "sale_price": "10.00",  # same price
                "catalogue_item": True,
            },
        )
        mock_notify.assert_not_called()


@pytest.mark.django_db
def test_no_notification_when_not_catalogue_item(
    client, staff_user, product, paired_with_product
):
    client.force_login(staff_user)
    product.catalogue_item = False
    product.sale_price = Decimal("10.00")
    product.save()
    with patch(
        "inventory.views._notify_remote_customer_product", return_value=True
    ) as mock_notify:
        client.post(
            reverse("inventory:product-update", args=[product.pk]),
            {
                "name": product.name,
                "description": "",
                "sale_price": "20.00",
                "catalogue_item": False,
            },
        )
        mock_notify.assert_not_called()


@pytest.mark.django_db
def test_no_notification_for_pending_paired_instance(client, staff_user, product):
    supplier = Supplier.objects.create(name="Pending Co")
    SupplierProduct.objects.create(
        supplier=supplier, product=product, cost=Decimal("5.00")
    )
    pi = PairedInstance.objects.create(
        name="Pending Remote",
        url="https://pending.example.com",
        api_key="",  # pending
    )
    pi.supplier = supplier
    pi.save()

    client.force_login(staff_user)
    with patch(
        "inventory.views._notify_remote_customer_product", return_value=True
    ) as mock_notify:
        client.post(
            reverse("inventory:product-update", args=[product.pk]),
            {
                "name": product.name,
                "description": "",
                "sale_price": "99.00",
                "catalogue_item": True,
            },
        )
        mock_notify.assert_not_called()


@pytest.mark.django_db
def test_warning_message_on_notification_failure(
    client, staff_user, product, paired_with_product
):
    client.force_login(staff_user)
    with (
        patch("inventory.views._notify_remote_customer_product", return_value=False),
        patch(
            "inventory.views._notify_remote_supplier_product_cost", return_value=False
        ),
    ):
        response = client.post(
            reverse("inventory:product-update", args=[product.pk]),
            {
                "name": product.name,
                "description": "",
                "sale_price": "25.00",
                "catalogue_item": True,
            },
            follow=True,
        )
        messages_list = list(response.context["messages"])
        assert any("failed to notify" in str(m).lower() for m in messages_list)
