"""Tests for main app views, logging formatter, audit helpers, and mixins."""

import json
import logging

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from inventory.models import Product
from main.logging_fmt import JsonFormatter

pytestmark = pytest.mark.integration


# ── HealthCheck ──────────────────────────────────────────────────────
class TestHealthCheck:
    def test_healthy(self, client, db):
        resp = client.get("/healthz/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["checks"]["database"] == "ok"


# ── Global Search ────────────────────────────────────────────────────
class TestGlobalSearch:
    @pytest.fixture
    def user(self, db):
        return User.objects.create_user("searcher")

    def test_empty_query(self, client, user):
        client.force_login(user)
        resp = client.get(reverse("global-search"))
        assert resp.status_code == 200

    def test_search_with_results(self, client, user):
        Product.objects.create(name="Searchable Widget")
        client.force_login(user)
        resp = client.get(reverse("global-search") + "?q=Searchable")
        assert resp.status_code == 200
        assert "Searchable Widget" in resp.content.decode()

    def test_search_no_results(self, client, user):
        client.force_login(user)
        resp = client.get(reverse("global-search") + "?q=ZZZZNOTFOUND")
        assert resp.status_code == 200


# ── JsonFormatter ────────────────────────────────────────────────────
@pytest.mark.unit
class TestJsonFormatter:
    def test_basic_format(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="hello %s",
            args=("world",),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["message"] == "hello world"
        assert data["level"] == "INFO"
        assert "timestamp" in data

    def test_with_exception(self):
        formatter = JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="an error",
            args=(),
            exc_info=exc_info,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert "exception" in data
        assert "ValueError" in str(data["exception"])

    def test_with_extra(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="extra test",
            args=(),
            exc_info=None,
        )
        record.extra = {"request_id": "abc123"}
        output = formatter.format(record)
        data = json.loads(output)
        assert data["request_id"] == "abc123"


# ── SoftDeleteMixin ──────────────────────────────────────────────────
class TestSoftDelete:
    def test_soft_delete_and_restore(self, db):
        p = Product.objects.create(name="Soft Del Product")
        pk = p.pk
        p.delete()
        # hidden from default manager
        assert not Product.objects.filter(pk=pk).exists()
        # visible in all_objects
        assert Product.all_objects.filter(pk=pk).exists()
        # restore
        p_deleted = Product.all_objects.get(pk=pk)
        p_deleted.restore()
        assert Product.objects.filter(pk=pk).exists()

    def test_queryset_dead_and_alive(self, db):
        p = Product.objects.create(name="QS Test Product")
        p.delete()
        qs = Product.all_objects.all()
        assert qs.dead().filter(pk=p.pk).exists()  # type: ignore[attr-defined]
        assert not qs.alive().filter(pk=p.pk).exists()  # type: ignore[attr-defined]

    def test_hard_delete(self, db):
        p = Product.objects.create(name="Hard Del Product")
        pk = p.pk
        p_ref = Product.all_objects.get(pk=pk)
        p_ref.hard_delete()
        assert not Product.all_objects.filter(pk=pk).exists()

    def test_queryset_bulk_delete(self, db):
        p1 = Product.objects.create(name="Bulk1")
        p2 = Product.objects.create(name="Bulk2")
        Product.objects.filter(pk__in=[p1.pk, p2.pk]).delete()
        assert Product.all_objects.filter(pk=p1.pk, is_deleted=True).exists()
        assert Product.objects.filter(pk=p1.pk).count() == 0

    def test_queryset_hard_delete(self, db):
        p = Product.objects.create(name="QS Hard Del")
        pk = p.pk
        Product.all_objects.filter(pk=pk).hard_delete()  # type: ignore[attr-defined]
        assert not Product.all_objects.filter(pk=pk).exists()


# ── Audit helper ─────────────────────────────────────────────────────
class TestAuditLogFieldChanges:
    def test_logs_changes(self, db):
        from main.audit import log_field_changes
        from main.models import AuditLog

        p = Product.objects.create(name="Audit Prod", sale_price=10)
        p.sale_price = 20
        log_field_changes(p, ["sale_price"])
        assert AuditLog.objects.filter(field_name="sale_price").exists()

    def test_no_log_for_unchanged(self, db):
        from main.audit import log_field_changes
        from main.models import AuditLog

        p = Product.objects.create(name="Unchanged Prod", sale_price=10)
        log_field_changes(p, ["sale_price"])
        assert not AuditLog.objects.filter(field_name="sale_price").exists()

    def test_no_log_when_pk_missing_from_db(self, db):
        """log_field_changes silently returns when the row no longer exists."""
        from main.audit import log_field_changes
        from main.models import AuditLog

        p = Product.objects.create(name="Vanishing Prod", sale_price=5)
        Product.all_objects.filter(pk=p.pk).hard_delete()  # type: ignore[attr-defined]
        p.sale_price = 99
        log_field_changes(p, ["sale_price"])
        assert not AuditLog.objects.exists()


# ── Model __str__ methods ────────────────────────────────────────────
class TestModelStrMethods:
    def test_audit_log_str(self, db):
        from django.contrib.contenttypes.models import ContentType

        from main.models import AuditLog

        p = Product.objects.create(name="Str Product")
        ct = ContentType.objects.get_for_model(Product)
        log = AuditLog.objects.create(
            content_type=ct, object_id=p.pk, field_name="name"
        )
        assert "name" in str(log)

    def test_webhook_endpoint_str(self, db):
        from config.models import WebhookEndpoint

        ep = WebhookEndpoint.objects.create(
            name="StrHook", url="https://example.com/hook", events=[]
        )
        assert str(ep) == "StrHook"

    def test_webhook_endpoint_secret_preview(self, db):
        from config.models import WebhookEndpoint

        ep = WebhookEndpoint.objects.create(
            name="PreviewHook",
            url="https://example.com/hook",
            secret="abcdefghijklmnop",
            events=[],
        )
        assert ep.secret_preview.startswith("abcdefgh")

    def test_webhook_delivery_str(self, db):
        from config.models import WebhookDelivery, WebhookEndpoint

        ep = WebhookEndpoint.objects.create(
            name="DelHook", url="https://example.com/hook", events=[]
        )
        d = WebhookDelivery.objects.create(
            endpoint=ep,
            event_type="order.created",
            payload={"id": 1},
            success=True,
        )
        s = str(d)
        assert "✓" in s
        assert "order.created" in s

    def test_paired_instance_str(self, db):
        from config.models import PairedInstance

        pi = PairedInstance.objects.create(name="TestPair", url="https://example.com")
        assert str(pi) == "TestPair"

    def test_finance_dashboard_snapshot_str(self, db):
        from finance.models import FinanceDashboardSnapshot

        snap = FinanceDashboardSnapshot.objects.create()
        assert "Dashboard snapshot" in str(snap)


# ── Error views ──────────────────────────────────────────────────────
class TestErrorViews:
    def test_custom_500(self, rf, db):
        from main.error_views import custom_500

        request = rf.get("/")
        resp = custom_500(request)
        assert resp.status_code == 500


# ── safe_redirect fallback ───────────────────────────────────────────
@pytest.mark.unit
class TestSafeRedirect:
    def test_unsafe_url_uses_fallback(self):
        from main.utils import safe_redirect

        resp = safe_redirect("https://evil.example.com")
        assert resp.status_code == 302
        assert resp.url == "/"


# ── AddressMixin properties ──────────────────────────────────────────
class TestAddressMixin:
    def test_full_address_and_alias(self, db):
        from sales.models import Customer

        c = Customer.objects.create(
            name="Addr Customer",
            address_line_1="123 Main St",
            city="Springfield",
            country="US",
        )
        assert "123 Main St" in c.full_address
        assert c.address == c.full_address


# ── Finance signal edge cases ────────────────────────────────────────
class TestFinanceSignal:
    def test_recursive_guard(self, db):
        """Recursive call is short-circuited by the thread-local guard."""
        from finance.signals import _refresh_finance_cache, _state

        _state.refreshing = True
        try:
            _refresh_finance_cache(sender=Product, instance=None)
        finally:
            _state.refreshing = False

    def test_exception_handling(self, db):
        """Exception during refresh is caught and logged."""
        from unittest.mock import patch

        from finance.signals import _refresh_finance_cache

        with patch(
            "finance.services.refresh_finance_dashboard_cache",
            side_effect=RuntimeError("boom"),
        ):
            # Should not raise
            _refresh_finance_cache(sender=Product, instance=None)

    def test_no_log_for_new_instance(self, db):
        from main.audit import log_field_changes
        from main.models import AuditLog

        p = Product(name="New Prod")
        log_field_changes(p, ["name"])
        assert AuditLog.objects.count() == 0
