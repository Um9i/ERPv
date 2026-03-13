from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse

from config.models import PairedInstance
from inventory.models import Product
from procurement.models import Supplier, SupplierProduct

pytestmark = pytest.mark.integration


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
        supplier=supplier, product=product, cost=Decimal("10.00")
    )
    pi = PairedInstance.objects.create(
        name="Remote", url="https://remote.example.com", api_key="theirkey"
    )
    pi.supplier = supplier
    pi.save()
    return pi


@pytest.mark.django_db
def test_price_change_notifies_both_customer_product_and_supplier_product(
    client, staff_user, product, paired_with_product
):
    client.force_login(staff_user)
    with (
        patch(
            "inventory.views._notify_remote_customer_product", return_value=True
        ) as mock_cp,
        patch(
            "inventory.views._notify_remote_supplier_product_cost", return_value=True
        ) as mock_sp,
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
        mock_cp.assert_called_once_with(paired_with_product, "Widget", Decimal("15.00"))
        mock_sp.assert_called_once_with(paired_with_product, "Widget", Decimal("15.00"))


@pytest.mark.django_db
def test_inbound_notify_updates_supplier_product_cost(client, product):
    supplier = Supplier.objects.create(name="Remote Co")
    sp = SupplierProduct.objects.create(
        supplier=supplier, product=product, cost=Decimal("10.00")
    )
    pi = PairedInstance.objects.create(
        name="Remote",
        url="https://remote.example.com",
        api_key="theirkey",
        our_key="ourkey",
    )
    pi.supplier = supplier
    pi.save()

    response = client.post(
        reverse("procurement:api-notify-supplier-product"),
        data='{"product_name": "Widget", "cost": "22.99"}',
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer ourkey",
    )
    assert response.status_code == 200
    sp.refresh_from_db()
    assert sp.cost == Decimal("22.99")


@pytest.mark.django_db
def test_inbound_notify_rejects_unknown_key(client, product):
    response = client.post(
        reverse("procurement:api-notify-supplier-product"),
        data='{"product_name": "Widget", "cost": "22.99"}',
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer wrongkey",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_inbound_notify_returns_400_if_supplier_not_linked(client, product):
    PairedInstance.objects.create(
        name="Remote",
        url="https://remote.example.com",
        api_key="theirkey",
        our_key="ourkey",
        # no supplier linked
    )
    response = client.post(
        reverse("procurement:api-notify-supplier-product"),
        data='{"product_name": "Widget", "cost": "22.99"}',
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer ourkey",
    )
    assert response.status_code == 400
    assert "Supplier not linked" in response.json()["error"]


@pytest.mark.django_db
def test_inbound_notify_returns_400_if_product_not_found(client, product):
    supplier = Supplier.objects.create(name="Remote Co")
    pi = PairedInstance.objects.create(
        name="Remote",
        url="https://remote.example.com",
        api_key="theirkey",
        our_key="ourkey",
    )
    pi.supplier = supplier
    pi.save()

    response = client.post(
        reverse("procurement:api-notify-supplier-product"),
        data='{"product_name": "Nonexistent", "cost": "22.99"}',
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer ourkey",
    )
    assert response.status_code == 400
    assert "SupplierProduct not found" in response.json()["error"]
