"""Permission & authentication tests.

Covers:
- LoginRequiredMiddleware redirects for unauthenticated users
- Staff-only views (UserPassesTestMixin) reject non-staff users
- Bearer token authentication on API endpoints
- Public endpoints remain accessible without auth
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from config.models import PairedInstance
from procurement.models import Supplier

User = get_user_model()


# ── fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def anon_client():
    """Unauthenticated client."""
    return Client()


@pytest.fixture
def normal_user(db):
    return User.objects.create_user(username="user", password="pass")


@pytest.fixture
def normal_client(normal_user):
    c = Client()
    c.force_login(normal_user)
    return c


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(username="staffuser", is_staff=True)


@pytest.fixture
def staff_client(staff_user):
    c = Client()
    c.force_login(staff_user)
    return c


@pytest.fixture
def paired_instance(db):
    supplier = Supplier.objects.create(name="Paired Supplier")
    pi = PairedInstance.objects.create(
        name="Remote Instance",
        url="https://remote.example.com",
        supplier=supplier,
    )
    return pi


# ── Middleware: unauthenticated redirects ─────────────────────────────────


class TestLoginRequiredMiddleware:
    """Unauthenticated requests to protected paths redirect to login."""

    PROTECTED_URLS = [
        "/dashboards/",
        "/inventory/",
        "/procurement/",
        "/sales/",
        "/production/",
        "/finance/",
        "/config/company/",
    ]

    @pytest.mark.django_db
    @pytest.mark.parametrize("url", PROTECTED_URLS)
    def test_anon_redirected_to_login(self, anon_client, url):
        resp = anon_client.get(url)
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url

    @pytest.mark.django_db
    @pytest.mark.parametrize("url", PROTECTED_URLS)
    def test_anon_redirect_includes_next(self, anon_client, url):
        resp = anon_client.get(url)
        assert f"next={url}" in resp.url


class TestPublicEndpoints:
    """Endpoints that should be accessible without login."""

    @pytest.mark.django_db
    def test_home_accessible(self, anon_client):
        resp = anon_client.get("/")
        assert resp.status_code == 200

    @pytest.mark.django_db
    def test_healthz_accessible(self, anon_client):
        resp = anon_client.get("/healthz/")
        assert resp.status_code == 200

    @pytest.mark.django_db
    def test_login_page_accessible(self, anon_client):
        resp = anon_client.get("/accounts/login/")
        assert resp.status_code == 200


# ── Authenticated but non-staff users ────────────────────────────────────


class TestAuthenticatedAccess:
    """Logged-in (non-staff) users can access regular views."""

    @pytest.mark.django_db
    def test_dashboard_accessible(self, normal_client):
        resp = normal_client.get("/dashboards/")
        assert resp.status_code == 200

    @pytest.mark.django_db
    def test_inventory_accessible(self, normal_client):
        resp = normal_client.get("/inventory/")
        assert resp.status_code == 200


# ── Staff-only views ─────────────────────────────────────────────────────


class TestStaffOnlyViews:
    """Views with UserPassesTestMixin(is_staff) reject non-staff users."""

    STAFF_ONLY_URLS = [
        "/config/company/",
        "/config/paired/",
    ]

    @pytest.mark.django_db
    @pytest.mark.parametrize("url", STAFF_ONLY_URLS)
    def test_non_staff_forbidden(self, normal_client, url):
        resp = normal_client.get(url)
        assert resp.status_code == 403

    @pytest.mark.django_db
    @pytest.mark.parametrize("url", STAFF_ONLY_URLS)
    def test_staff_allowed(self, staff_client, url):
        resp = staff_client.get(url)
        assert resp.status_code == 200

    @pytest.mark.django_db
    def test_paired_create_non_staff_forbidden(self, normal_client):
        resp = normal_client.get("/config/paired/create/")
        assert resp.status_code == 403

    @pytest.mark.django_db
    def test_paired_create_staff_allowed(self, staff_client):
        resp = staff_client.get("/config/paired/create/")
        assert resp.status_code == 200


# ── Bearer token API authentication ──────────────────────────────────────


class TestBearerTokenAuth:
    """API endpoints that require Bearer token reject bad/missing tokens."""

    # ── Company API (/config/api/company/) ────────────────────────────

    @pytest.mark.django_db
    def test_company_api_no_token(self, anon_client):
        resp = anon_client.get("/config/api/company/")
        assert resp.status_code == 401

    @pytest.mark.django_db
    def test_company_api_bad_token(self, anon_client, paired_instance):
        resp = anon_client.get(
            "/config/api/company/",
            HTTP_AUTHORIZATION="Bearer wrong-key",
        )
        assert resp.status_code == 401

    @pytest.mark.django_db
    def test_company_api_valid_token(self, anon_client, paired_instance):
        resp = anon_client.get(
            "/config/api/company/",
            HTTP_AUTHORIZATION=f"Bearer {paired_instance.our_key}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data

    @pytest.mark.django_db
    def test_company_api_no_bearer_prefix(self, anon_client, paired_instance):
        resp = anon_client.get(
            "/config/api/company/",
            HTTP_AUTHORIZATION=paired_instance.our_key,
        )
        assert resp.status_code == 401

    # ── Catalogue API (/inventory/api/catalogue/) ─────────────────────

    @pytest.mark.django_db
    def test_catalogue_api_no_token(self, anon_client):
        resp = anon_client.get("/inventory/api/catalogue/")
        assert resp.status_code == 401

    @pytest.mark.django_db
    def test_catalogue_api_bad_token(self, anon_client, paired_instance):
        resp = anon_client.get(
            "/inventory/api/catalogue/",
            HTTP_AUTHORIZATION="Bearer invalid",
        )
        assert resp.status_code == 401

    @pytest.mark.django_db
    def test_catalogue_api_valid_token(self, anon_client, paired_instance):
        resp = anon_client.get(
            "/inventory/api/catalogue/",
            HTTP_AUTHORIZATION=f"Bearer {paired_instance.our_key}",
        )
        assert resp.status_code == 200

    # ── Notify Customer (/config/api/notify/customer/) ────────────────

    @pytest.mark.django_db
    def test_notify_customer_no_token(self, anon_client):
        resp = anon_client.post(
            "/config/api/notify/customer/",
            data=json.dumps({"name": "Acme"}),
            content_type="application/json",
        )
        assert resp.status_code == 401

    @pytest.mark.django_db
    def test_notify_customer_bad_token(self, anon_client, paired_instance):
        resp = anon_client.post(
            "/config/api/notify/customer/",
            data=json.dumps({"name": "Acme"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer bad-key",
        )
        assert resp.status_code == 401

    @pytest.mark.django_db
    def test_notify_customer_valid_token(self, anon_client, paired_instance):
        resp = anon_client.post(
            "/config/api/notify/customer/",
            data=json.dumps({"name": "New Customer"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {paired_instance.our_key}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["created"] is True

    # ── Notify Supplier Product (/procurement/api/notify/supplier-product/) ───

    @pytest.mark.django_db
    def test_notify_supplier_product_no_token(self, anon_client):
        resp = anon_client.post(
            "/procurement/api/notify/supplier-product/",
            data=json.dumps({"product_name": "Widget", "cost": "10.00"}),
            content_type="application/json",
        )
        assert resp.status_code == 401

    @pytest.mark.django_db
    def test_notify_supplier_product_bad_token(self, anon_client, paired_instance):
        resp = anon_client.post(
            "/procurement/api/notify/supplier-product/",
            data=json.dumps({"product_name": "Widget", "cost": "10.00"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer wrong",
        )
        assert resp.status_code == 401


# ── Internal API views (middleware-exempt, no token) ──────────────────────


class TestInternalApiViews:
    """Internal API views behave correctly with middleware and view-level auth."""

    @pytest.mark.django_db
    def test_inventory_list_api_requires_login(self, anon_client):
        """InventoryListApiView is at /inventory/inventories/api/ which is NOT
        under the /inventory/api/ exempt prefix, so middleware blocks anon."""
        resp = anon_client.get("/inventory/inventories/api/")
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url

    @pytest.mark.django_db
    def test_inventory_list_api_authed(self, normal_client):
        resp = normal_client.get("/inventory/inventories/api/")
        assert resp.status_code == 200

    @pytest.mark.django_db
    def test_catalogue_api_requires_token_despite_prefix(self, anon_client):
        """Catalogue API is under /inventory/api/ (middleware exempt) but
        still enforces Bearer token auth at the view level."""
        resp = anon_client.get("/inventory/api/catalogue/")
        assert resp.status_code == 401
