"""Tests for config.notifications remote notification functions."""

from unittest.mock import MagicMock, patch

import pytest

from config.models import CompanyConfig, PairedInstance

pytestmark = pytest.mark.unit


@pytest.fixture
def paired(db):
    return PairedInstance.objects.create(
        name="Notify Partner",
        url="https://partner.example.com",
        api_key="notify-key",
    )


@pytest.fixture
def _company(db):
    CompanyConfig.objects.create(
        name="Test Co",
        address_line_1="1 Test St",
        city="London",
        postal_code="SW1A 1AA",
        country="GB",
        phone="0123456789",
        email="test@example.com",
    )


class TestNotifyRemoteCustomer:
    @patch("config.notifications.httpx.post")
    def test_success(self, mock_post, paired, _company):
        from config.notifications import _notify_remote_customer

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = _notify_remote_customer(paired)
        assert result is True
        mock_post.assert_called_once()

    @patch("config.notifications.httpx.post")
    def test_failure(self, mock_post, paired, _company):
        from config.notifications import _notify_remote_customer

        mock_post.side_effect = Exception("connection refused")

        result = _notify_remote_customer(paired)
        assert result is False


class TestNotifyRemoteCustomerProduct:
    @patch("config.notifications.httpx.post")
    def test_success(self, mock_post, paired):
        from config.notifications import _notify_remote_customer_product

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = _notify_remote_customer_product(paired, "Widget", "12.50")
        assert result is True

    @patch("config.notifications.httpx.post")
    def test_failure(self, mock_post, paired):
        from config.notifications import _notify_remote_customer_product

        mock_post.side_effect = Exception("timeout")

        result = _notify_remote_customer_product(paired, "Widget", "12.50")
        assert result is False


class TestNotifyRemoteSupplierProductCost:
    @patch("config.notifications.httpx.post")
    def test_success(self, mock_post, paired):
        from config.notifications import _notify_remote_supplier_product_cost

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = _notify_remote_supplier_product_cost(paired, "Widget", "5.00")
        assert result is True

    @patch("config.notifications.httpx.post")
    def test_failure(self, mock_post, paired):
        from config.notifications import _notify_remote_supplier_product_cost

        mock_post.side_effect = Exception("error")

        result = _notify_remote_supplier_product_cost(paired, "Widget", "5.00")
        assert result is False


class TestNotifyRemotePurchaseOrder:
    @patch("config.notifications.httpx.post")
    def test_success(self, mock_post, paired):
        from config.notifications import _notify_remote_purchase_order
        from inventory.models import Product
        from procurement.models import (
            PurchaseOrder,
            PurchaseOrderLine,
            Supplier,
            SupplierProduct,
        )

        supplier = Supplier.objects.create(name="PO Notify Supplier")
        product = Product.objects.create(name="PO Notify Product")
        sp = SupplierProduct.objects.create(supplier=supplier, product=product, cost=10)
        po = PurchaseOrder.objects.create(supplier=supplier)
        PurchaseOrderLine.objects.create(
            purchase_order=po, product=sp, quantity=5, quantity_received=0
        )

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = _notify_remote_purchase_order(paired, po)
        assert result is True

    @patch("config.notifications.httpx.post")
    def test_failure(self, mock_post, paired):
        from config.notifications import _notify_remote_purchase_order
        from procurement.models import PurchaseOrder, Supplier

        supplier = Supplier.objects.create(name="Fail Supplier")
        po = PurchaseOrder.objects.create(supplier=supplier)

        mock_post.side_effect = Exception("error")

        result = _notify_remote_purchase_order(paired, po)
        assert result is False
