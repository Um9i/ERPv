"""Tests for webhook dispatch and retry logic."""

from unittest.mock import MagicMock, patch

import pytest

from config.models import WebhookEndpoint
from config.webhooks import _sign, dispatch_event

pytestmark = pytest.mark.unit


@pytest.fixture
def endpoint(db):
    return WebhookEndpoint.objects.create(
        name="Test Hook",
        url="https://hook.example.com/payload",
        secret="test-secret",
        events=["order.created", "stock.adjusted"],
    )


@pytest.fixture
def endpoint_no_secret(db):
    ep = WebhookEndpoint.objects.create(
        name="No Secret Hook",
        url="https://hook.example.com/payload2",
        events=["order.created"],
    )
    # Bypass save() which auto-generates a secret when blank
    WebhookEndpoint.objects.filter(pk=ep.pk).update(secret="")
    ep.refresh_from_db()
    return ep


class TestSign:
    def test_produces_hex_digest(self):
        sig = _sign(b'{"key":"value"}', "mysecret")
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA256 hex digest


class TestDispatchEvent:
    @patch("config.webhooks.time.sleep")
    @patch("config.webhooks.httpx.Client")
    def test_successful_delivery(self, mock_client_cls, mock_sleep, endpoint):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "OK"
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        dispatch_event("order.created", {"order_id": 1})

        mock_client.post.assert_called_once()
        mock_sleep.assert_not_called()

        from config.models import WebhookDelivery

        delivery = WebhookDelivery.objects.get(endpoint=endpoint)
        assert delivery.success is True
        assert delivery.response_status == 200

    @patch("config.webhooks.time.sleep")
    @patch("config.webhooks.httpx.Client")
    def test_skips_unsubscribed_events(self, mock_client_cls, mock_sleep, endpoint):
        dispatch_event("shipment.completed", {"id": 1})
        mock_client_cls.assert_not_called()

    @patch("config.webhooks.time.sleep")
    @patch("config.webhooks.httpx.Client")
    def test_skips_inactive_endpoint(self, mock_client_cls, mock_sleep, endpoint):
        endpoint.is_active = False
        endpoint.save()
        dispatch_event("order.created", {"id": 1})
        mock_client_cls.assert_not_called()

    @patch("config.webhooks.time.sleep")
    @patch("config.webhooks.httpx.Client")
    def test_retries_on_5xx(self, mock_client_cls, mock_sleep, endpoint):
        mock_resp_500 = MagicMock()
        mock_resp_500.status_code = 500
        mock_resp_500.text = "Internal Server Error"
        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_resp_200.text = "OK"

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = [mock_resp_500, mock_resp_200]
        mock_client_cls.return_value = mock_client

        dispatch_event("order.created", {"id": 1})

        assert mock_client.post.call_count == 2
        assert mock_sleep.call_count == 1

    @patch("config.webhooks.time.sleep")
    @patch("config.webhooks.httpx.Client")
    def test_no_retry_on_4xx(self, mock_client_cls, mock_sleep, endpoint):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        dispatch_event("order.created", {"id": 1})

        mock_client.post.assert_called_once()

        from config.models import WebhookDelivery

        delivery = WebhookDelivery.objects.get(endpoint=endpoint)
        assert delivery.success is False

    @patch("config.webhooks.time.sleep")
    @patch("config.webhooks.httpx.Client")
    def test_retries_on_network_error(self, mock_client_cls, mock_sleep, endpoint):
        import httpx

        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.text = "OK"

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = [
            httpx.ConnectError("connection refused"),
            mock_resp_ok,
        ]
        mock_client_cls.return_value = mock_client

        dispatch_event("order.created", {"id": 1})

        assert mock_client.post.call_count == 2

    @patch("config.webhooks.time.sleep")
    @patch("config.webhooks.httpx.Client")
    def test_exhausted_retries_logged(self, mock_client_cls, mock_sleep, endpoint):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Unavailable"

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        dispatch_event("order.created", {"id": 1})

        # 1 initial + 3 retries = 4 total
        assert mock_client.post.call_count == 4

        from config.models import WebhookDelivery

        delivery = WebhookDelivery.objects.get(endpoint=endpoint)
        assert delivery.success is False

    @patch("config.webhooks.time.sleep")
    @patch("config.webhooks.httpx.Client")
    def test_no_signature_header_without_secret(
        self, mock_client_cls, mock_sleep, endpoint_no_secret
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "OK"

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        dispatch_event("order.created", {"id": 1})

        call_args = mock_client.post.call_args
        headers = call_args.kwargs.get("headers", {})
        assert "X-Webhook-Signature" not in headers
