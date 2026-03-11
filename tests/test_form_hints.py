"""Tests for duplicate-check warnings and form help text / validation hints."""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from config.forms import CompanyConfigForm, PairedInstanceForm
from inventory.forms import ProductForm, StockTransferForm
from inventory.models import Inventory, Product, ProductionAllocated
from procurement.forms import (
    PurchaseOrderForm,
    PurchaseOrderLineForm,
    SupplierContactForm,
    SupplierProductForm,
)
from procurement.models import Supplier, SupplierProduct
from production.forms import (
    BillOfMaterialsForm,
    BOMItemForm,
    ProductionForm,
    ProductionUpdateForm,
)
from sales.forms import (
    CustomerContactForm,
    CustomerProductForm,
    SalesOrderForm,
    SalesOrderLineForm,
)


def _product(name):
    p = Product.objects.bulk_create([Product(name=name)])[0]
    Inventory.objects.bulk_create([Inventory(product=p)])
    ProductionAllocated.objects.bulk_create([ProductionAllocated(product=p)])
    return p


@pytest.fixture
def user(db):
    return User.objects.create_user(username="tester")


# ──────────────────────────────────────────────────────────────────────────────
# Duplicate-check AJAX endpoint
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSupplierProductCheck:
    def test_no_duplicate_returns_false(self, client, user):
        client.force_login(user)
        supplier = Supplier.objects.create(name="S")
        product = _product("P")
        url = reverse("procurement:supplier-product-check")
        resp = client.get(url, {"supplier": supplier.pk, "product": product.pk})
        assert resp.status_code == 200
        assert resp.json() == {"exists": False}

    def test_duplicate_returns_true(self, client, user):
        client.force_login(user)
        supplier = Supplier.objects.create(name="S")
        product = _product("P")
        SupplierProduct.objects.create(supplier=supplier, product=product, cost=10)
        url = reverse("procurement:supplier-product-check")
        resp = client.get(url, {"supplier": supplier.pk, "product": product.pk})
        assert resp.status_code == 200
        assert resp.json() == {"exists": True}

    def test_exclude_current_pk(self, client, user):
        client.force_login(user)
        supplier = Supplier.objects.create(name="S")
        product = _product("P")
        sp = SupplierProduct.objects.create(supplier=supplier, product=product, cost=10)
        url = reverse("procurement:supplier-product-check")
        resp = client.get(
            url,
            {"supplier": supplier.pk, "product": product.pk, "exclude": sp.pk},
        )
        assert resp.status_code() == 200 if False else resp.status_code == 200
        assert resp.json() == {"exists": False}

    def test_missing_params_returns_false(self, client, user):
        client.force_login(user)
        url = reverse("procurement:supplier-product-check")
        resp = client.get(url)
        assert resp.json() == {"exists": False}

    def test_requires_login(self, client):
        url = reverse("procurement:supplier-product-check")
        resp = client.get(url, {"supplier": 1, "product": 1})
        assert resp.status_code == 302  # redirect to login

    def test_duplicate_warning_in_template(self, client, user):
        client.force_login(user)
        url = reverse("procurement:supplier-product-create")
        resp = client.get(url)
        content = resp.content.decode()
        assert "duplicate-warning" in content
        assert "This supplier already carries the selected product" in content


# ──────────────────────────────────────────────────────────────────────────────
# Help text presence
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestHelpText:
    """Verify that complex fields have help_text set."""

    def test_supplier_contact_help_text(self):
        form = SupplierContactForm()
        assert form.fields["email"].help_text
        assert form.fields["phone"].help_text

    def test_customer_contact_help_text(self):
        form = CustomerContactForm()
        assert form.fields["email"].help_text
        assert form.fields["phone"].help_text

    def test_supplier_product_cost_help_text(self):
        form = SupplierProductForm()
        assert form.fields["cost"].help_text

    def test_customer_product_price_help_text(self):
        form = CustomerProductForm()
        assert form.fields["price"].help_text

    def test_purchase_order_due_date_help_text(self):
        form = PurchaseOrderForm()
        assert form.fields["due_date"].help_text

    def test_purchase_order_line_quantity_help_text(self):
        form = PurchaseOrderLineForm()
        assert form.fields["quantity"].help_text

    def test_sales_order_ship_by_date_help_text(self):
        form = SalesOrderForm()
        assert form.fields["ship_by_date"].help_text

    def test_sales_order_line_quantity_help_text(self):
        form = SalesOrderLineForm()
        assert form.fields["quantity"].help_text

    def test_product_form_help_text(self):
        form = ProductForm()
        assert form.fields["sku"].help_text
        assert form.fields["sale_price"].help_text
        assert form.fields["catalogue_item"].help_text

    def test_stock_transfer_help_text(self):
        form = StockTransferForm()
        assert form.fields["quantity"].help_text
        assert form.fields["note"].help_text

    def test_bom_form_help_text(self):
        form = BillOfMaterialsForm()
        assert form.fields["production_cost"].help_text

    def test_bom_item_quantity_help_text(self):
        form = BOMItemForm()
        assert form.fields["quantity"].help_text

    def test_production_form_help_text(self):
        form = ProductionForm()
        assert form.fields["quantity"].help_text
        assert form.fields["due_date"].help_text

    def test_production_update_form_help_text(self):
        form = ProductionUpdateForm()
        assert form.fields["quantity"].help_text
        assert form.fields["due_date"].help_text
        assert form.fields["complete"].help_text

    def test_company_config_help_text(self):
        form = CompanyConfigForm()
        assert form.fields["website"].help_text
        assert form.fields["vat_number"].help_text

    def test_paired_instance_help_text(self):
        form = PairedInstanceForm()
        assert form.fields["url"].help_text
        assert form.fields["notes"].help_text


# ──────────────────────────────────────────────────────────────────────────────
# HTML5 widget attributes
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestWidgetAttrs:
    """Verify min/step attributes are present on numeric inputs."""

    def test_supplier_product_cost_attrs(self):
        form = SupplierProductForm()
        attrs = form.fields["cost"].widget.attrs
        assert attrs.get("step") == "0.01"
        assert attrs.get("min") == "0.01"

    def test_customer_product_price_attrs(self):
        form = CustomerProductForm()
        attrs = form.fields["price"].widget.attrs
        assert attrs.get("step") == "0.01"
        assert attrs.get("min") == "0.01"

    def test_product_sale_price_attrs(self):
        form = ProductForm()
        attrs = form.fields["sale_price"].widget.attrs
        assert attrs.get("step") == "0.01"
        assert attrs.get("min") == "0.01"

    def test_bom_production_cost_attrs(self):
        form = BillOfMaterialsForm()
        attrs = form.fields["production_cost"].widget.attrs
        assert attrs.get("step") == "0.01"
        assert attrs.get("min") == "0"
