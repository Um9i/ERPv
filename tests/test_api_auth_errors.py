"""Tests for API authentication edge-cases and error scenarios.

Fills gaps not covered by existing endpoint-specific test files:
- Empty / whitespace-only Bearer tokens
- Unsupported HTTP methods on GET-only and POST-only endpoints
- Malformed / invalid JSON bodies on POST endpoints
- Missing required fields, invalid numeric values
- Supplier-not-linked and SupplierProduct-not-found error paths
- Session-based internal API views (Production, Inventory)
"""

import json
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from config.models import PairedInstance
from inventory.models import Inventory, Product
from procurement.models import Supplier, SupplierProduct
from production.models import Production
from sales.models import Customer

pytestmark = pytest.mark.integration

User = get_user_model()


# ── fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def anon(db):
    return Client()


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(username="staff", is_staff=True)


@pytest.fixture
def authed(staff_user):
    c = Client()
    c.force_login(staff_user)
    return c


@pytest.fixture
def paired(db):
    return PairedInstance.objects.create(
        name="Remote",
        url="https://remote.example.com",
        api_key="their-key",
    )


@pytest.fixture
def paired_with_customer(paired):
    customer = Customer.objects.create(name="Linked Customer")
    paired.customer = customer
    paired.save(update_fields=["customer"])
    return paired


@pytest.fixture
def paired_with_supplier(paired):
    supplier = Supplier.objects.create(name="Linked Supplier")
    paired.supplier = supplier
    paired.save(update_fields=["supplier"])
    return paired


@pytest.fixture
def product(db):
    return Product.objects.create(name="Widget", sale_price=Decimal("10.00"))


# ── CompanyApiView (/config/api/company/) ─────────────────────────────────


COMPANY_URL = "/config/api/company/"


class TestCompanyApiErrors:
    @pytest.mark.django_db
    def test_empty_bearer_token_returns_401(self, anon, paired):
        resp = anon.get(COMPANY_URL, HTTP_AUTHORIZATION="Bearer ")
        assert resp.status_code == 401

    @pytest.mark.django_db
    def test_post_method_not_allowed(self, anon, paired):
        resp = anon.post(
            COMPANY_URL,
            data="{}",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {paired.our_key}",
        )
        assert resp.status_code == 405

    @pytest.mark.django_db
    def test_put_method_not_allowed(self, anon, paired):
        resp = anon.put(
            COMPANY_URL,
            data="{}",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {paired.our_key}",
        )
        assert resp.status_code == 405


# ── NotifyCustomerView (/config/api/notify/customer/) ─────────────────────


NOTIFY_CUSTOMER_URL = "/config/api/notify/customer/"


class TestNotifyCustomerErrors:
    @pytest.mark.django_db
    def test_invalid_json_body_returns_400(self, anon, paired):
        resp = anon.post(
            NOTIFY_CUSTOMER_URL,
            data="not json at all{",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {paired.our_key}",
        )
        assert resp.status_code == 400
        body = resp.json()
        assert "detail" in body or "error" in body  # DRF parse-error key

    @pytest.mark.django_db
    def test_empty_body_returns_400(self, anon, paired):
        resp = anon.post(
            NOTIFY_CUSTOMER_URL,
            data="",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {paired.our_key}",
        )
        assert resp.status_code == 400

    @pytest.mark.django_db
    def test_get_method_not_allowed(self, anon, paired):
        resp = anon.get(
            NOTIFY_CUSTOMER_URL,
            HTTP_AUTHORIZATION=f"Bearer {paired.our_key}",
        )
        assert resp.status_code == 405


# ── NotifyCustomerProductView (/config/api/notify/customer-product/) ──────


NOTIFY_CP_URL = "/config/api/notify/customer-product/"


class TestNotifyCustomerProductErrors:
    @pytest.mark.django_db
    def test_no_auth_returns_401(self, anon):
        resp = anon.post(
            NOTIFY_CP_URL,
            data=json.dumps({"product_name": "Widget", "price": "10.00"}),
            content_type="application/json",
        )
        assert resp.status_code == 401

    @pytest.mark.django_db
    def test_wrong_key_returns_401(self, anon, paired_with_customer):
        resp = anon.post(
            NOTIFY_CP_URL,
            data=json.dumps({"product_name": "Widget", "price": "10.00"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer wrong-key",
        )
        assert resp.status_code == 401

    @pytest.mark.django_db
    def test_invalid_json_returns_400(self, anon, paired_with_customer):
        resp = anon.post(
            NOTIFY_CP_URL,
            data="{bad json",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {paired_with_customer.our_key}",
        )
        assert resp.status_code == 400
        body = resp.json()
        assert "detail" in body or "error" in body

    @pytest.mark.django_db
    def test_invalid_price_returns_400(self, anon, paired_with_customer, product):
        resp = anon.post(
            NOTIFY_CP_URL,
            data=json.dumps({"product_name": "Widget", "price": "not-a-number"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {paired_with_customer.our_key}",
        )
        assert resp.status_code == 400
        assert "price" in resp.json()["error"]

    @pytest.mark.django_db
    def test_missing_product_name_returns_400(self, anon, paired_with_customer):
        resp = anon.post(
            NOTIFY_CP_URL,
            data=json.dumps({"price": "10.00"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {paired_with_customer.our_key}",
        )
        assert resp.status_code == 400
        assert "product_name" in resp.json()["error"]

    @pytest.mark.django_db
    def test_get_method_not_allowed(self, anon, paired_with_customer):
        resp = anon.get(
            NOTIFY_CP_URL,
            HTTP_AUTHORIZATION=f"Bearer {paired_with_customer.our_key}",
        )
        assert resp.status_code == 405


# ── CatalogueApiView (/inventory/api/catalogue/) ─────────────────────────


CATALOGUE_URL = "/inventory/api/catalogue/"


class TestCatalogueApiErrors:
    @pytest.mark.django_db
    def test_empty_bearer_token_returns_401(self, anon, paired):
        resp = anon.get(CATALOGUE_URL, HTTP_AUTHORIZATION="Bearer ")
        assert resp.status_code == 401

    @pytest.mark.django_db
    def test_post_method_not_allowed(self, anon, paired):
        resp = anon.post(
            CATALOGUE_URL,
            data="{}",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {paired.our_key}",
        )
        assert resp.status_code == 405

    @pytest.mark.django_db
    def test_empty_catalogue_returns_empty_list(self, anon, paired):
        resp = anon.get(
            CATALOGUE_URL,
            HTTP_AUTHORIZATION=f"Bearer {paired.our_key}",
        )
        assert resp.status_code == 200
        assert resp.json() == []


# ── NotifySupplierProductView (/procurement/api/notify/supplier-product/) ─


NOTIFY_SP_URL = "/procurement/api/notify/supplier-product/"


class TestNotifySupplierProductErrors:
    @pytest.mark.django_db
    def test_supplier_not_linked_returns_400(self, anon, paired, product):
        # paired instance has no supplier linked
        resp = anon.post(
            NOTIFY_SP_URL,
            data=json.dumps({"product_name": "Widget", "cost": "5.00"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {paired.our_key}",
        )
        assert resp.status_code == 400
        assert "Supplier not linked" in resp.json()["error"]

    @pytest.mark.django_db
    def test_invalid_json_returns_400(self, anon, paired_with_supplier):
        resp = anon.post(
            NOTIFY_SP_URL,
            data="{{corrupt",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {paired_with_supplier.our_key}",
        )
        assert resp.status_code == 400
        body = resp.json()
        assert "detail" in body or "error" in body

    @pytest.mark.django_db
    def test_invalid_cost_returns_400(self, anon, paired_with_supplier, product):
        SupplierProduct.objects.create(
            supplier=paired_with_supplier.supplier,
            product=product,
            cost=Decimal("10.00"),
        )
        resp = anon.post(
            NOTIFY_SP_URL,
            data=json.dumps({"product_name": "Widget", "cost": "abc"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {paired_with_supplier.our_key}",
        )
        assert resp.status_code == 400
        assert "cost" in resp.json()["error"]

    @pytest.mark.django_db
    def test_missing_product_name_returns_400(self, anon, paired_with_supplier):
        resp = anon.post(
            NOTIFY_SP_URL,
            data=json.dumps({"cost": "5.00"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {paired_with_supplier.our_key}",
        )
        assert resp.status_code == 400
        assert "product_name" in resp.json()["error"]

    @pytest.mark.django_db
    def test_supplier_product_not_found_returns_400(
        self, anon, paired_with_supplier, product
    ):
        # product exists but no SupplierProduct row for this supplier
        resp = anon.post(
            NOTIFY_SP_URL,
            data=json.dumps({"product_name": "Widget", "cost": "5.00"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {paired_with_supplier.our_key}",
        )
        assert resp.status_code == 400
        assert "SupplierProduct not found" in resp.json()["error"]

    @pytest.mark.django_db
    def test_no_auth_header_returns_401(self, anon):
        resp = anon.post(
            NOTIFY_SP_URL,
            data=json.dumps({"product_name": "Widget", "cost": "5.00"}),
            content_type="application/json",
        )
        assert resp.status_code == 401


# ── ProductionListApiView (/production/jobs/api/) ─────────────────────────


PRODUCTION_API_URL = "/production/jobs/api/"


class TestProductionListApi:
    @pytest.mark.django_db
    def test_anon_redirected_to_login(self, anon):
        resp = anon.get(PRODUCTION_API_URL)
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url

    @pytest.mark.django_db
    def test_authed_returns_productions(self, authed, product):
        Production.objects.create(product=product, quantity=10)
        resp = authed.get(PRODUCTION_API_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert "productions" in data
        assert len(data["productions"]) == 1
        assert data["productions"][0]["product"] == "Widget"
        assert data["productions"][0]["quantity"] == 10

    @pytest.mark.django_db
    def test_q_param_filters_by_product_name(self, authed, product):
        Production.objects.create(product=product, quantity=5)
        other = Product.objects.create(name="Gadget", sale_price=Decimal("20.00"))
        Production.objects.create(product=other, quantity=3)

        resp = authed.get(PRODUCTION_API_URL, {"q": "Widget"})
        data = resp.json()
        assert len(data["productions"]) == 1
        assert data["productions"][0]["product"] == "Widget"

    @pytest.mark.django_db
    def test_excludes_complete_jobs(self, authed, product):
        Production.objects.create(product=product, quantity=5, complete=True)
        resp = authed.get(PRODUCTION_API_URL)
        assert resp.json()["productions"] == []

    @pytest.mark.django_db
    def test_empty_result_returns_empty_list(self, authed):
        resp = authed.get(PRODUCTION_API_URL)
        assert resp.status_code == 200
        assert resp.json()["productions"] == []


# ── InventoryListApiView (/inventory/inventories/api/) ────────────────────


INVENTORY_API_URL = "/inventory/inventories/api/"


class TestInventoryListApi:
    @pytest.mark.django_db
    def test_returns_inventory_data(self, authed, product):
        inv = Inventory.objects.get(product=product)
        inv.quantity = 42
        inv.save(update_fields=["quantity"])
        resp = authed.get(INVENTORY_API_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["product"] == "Widget"
        assert data[0]["quantity"] == 42

    @pytest.mark.django_db
    def test_empty_inventory_returns_empty_list(self, authed):
        resp = authed.get(INVENTORY_API_URL)
        assert resp.status_code == 200
        assert resp.json() == []
