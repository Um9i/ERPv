"""Form validation unit tests — email, phone regex, date, cross-field rules."""

from decimal import Decimal

import pytest

from config.forms import CompanyConfigForm, CompletePairingForm
from inventory.forms import InventoryAdjustForm, ProductForm
from inventory.models import Inventory, Product, ProductionAllocated
from procurement.forms import (
    PurchaseOrderLineForm,
    SupplierContactForm,
    SupplierForm,
    SupplierProductForm,
)
from procurement.models import Supplier, SupplierProduct
from production.forms import BOMItemForm, ProductionForm
from sales.forms import (
    CustomerContactForm,
    CustomerForm,
    CustomerProductForm,
    SalesOrderLineForm,
)
from sales.models import Customer


def _product_with_deps(name, quantity=0, sale_price=None):
    p = Product.objects.bulk_create([Product(name=name, sale_price=sale_price)])[0]
    Inventory.objects.bulk_create([Inventory(product=p, quantity=quantity)])
    ProductionAllocated.objects.bulk_create([ProductionAllocated(product=p)])
    return p


# ──────────────────────────────────────────────────────────────────────────────
# Phone regex validation
# ──────────────────────────────────────────────────────────────────────────────


class TestPhoneValidation:
    r"""Phone regex: ^\+?[\d\s\-().]{7,64}$"""

    @pytest.mark.django_db
    def test_valid_phone_numbers(self):
        valid = [
            "+1 (555) 123-4567",
            "020 7946 0958",
            "+44 20 7946 0958",
            "555-1234567",
            "(555) 123 4567",
            "1234567",
        ]
        for phone in valid:
            form = CustomerForm(data={"name": "Test", "phone": phone})
            form.is_valid()
            assert "phone" not in form.errors, f"Valid phone rejected: {phone}"

    @pytest.mark.django_db
    def test_invalid_phone_numbers(self):
        invalid = [
            "abc",
            "12345",  # too short (<7)
            "+1-abc-def",
            "!@#$%^&*",
        ]
        for phone in invalid:
            form = CustomerForm(data={"name": "Test", "phone": phone})
            form.is_valid()
            assert "phone" in form.errors, f"Invalid phone accepted: {phone}"

    @pytest.mark.django_db
    def test_phone_validation_on_supplier_form(self):
        form = SupplierForm(data={"name": "Test Supplier", "phone": "12345"})
        form.is_valid()
        assert "phone" in form.errors

    @pytest.mark.django_db
    def test_phone_optional(self):
        form = CustomerForm(data={"name": "Test"})
        form.is_valid()
        assert "phone" not in form.errors


# ──────────────────────────────────────────────────────────────────────────────
# Email validation
# ──────────────────────────────────────────────────────────────────────────────


class TestEmailValidation:
    @pytest.mark.django_db
    def test_valid_email(self):
        form = CustomerForm(data={"name": "Test", "email": "user@example.com"})
        form.is_valid()
        assert "email" not in form.errors

    @pytest.mark.django_db
    def test_invalid_email(self):
        form = CustomerForm(data={"name": "Test", "email": "not-an-email"})
        form.is_valid()
        assert "email" in form.errors

    @pytest.mark.django_db
    def test_email_optional(self):
        form = CustomerForm(data={"name": "Test"})
        form.is_valid()
        assert "email" not in form.errors

    @pytest.mark.django_db
    def test_supplier_contact_invalid_email(self):
        form = SupplierContactForm(data={"name": "Contact", "email": "bad@@email"})
        form.is_valid()
        assert "email" in form.errors

    @pytest.mark.django_db
    def test_customer_contact_valid_email(self):
        customer = Customer.objects.create(name="CC_Customer")
        form = CustomerContactForm(
            data={"name": "Contact", "customer": customer.pk, "email": "a@b.com"}
        )
        form.is_valid()
        assert "email" not in form.errors


# ──────────────────────────────────────────────────────────────────────────────
# Name / required field validation
# ──────────────────────────────────────────────────────────────────────────────


class TestNameValidation:
    @pytest.mark.django_db
    def test_customer_name_required(self):
        form = CustomerForm(data={"name": ""})
        assert not form.is_valid()
        assert "name" in form.errors

    @pytest.mark.django_db
    def test_customer_name_whitespace_only(self):
        form = CustomerForm(data={"name": "   "})
        assert not form.is_valid()
        assert "name" in form.errors

    @pytest.mark.django_db
    def test_supplier_name_required(self):
        form = SupplierForm(data={"name": ""})
        assert not form.is_valid()
        assert "name" in form.errors

    @pytest.mark.django_db
    def test_supplier_contact_name_required(self):
        form = SupplierContactForm(data={"name": ""})
        assert not form.is_valid()
        assert "name" in form.errors

    @pytest.mark.django_db
    def test_customer_contact_name_required(self):
        form = CustomerContactForm(data={"name": ""})
        assert not form.is_valid()
        assert "name" in form.errors

    @pytest.mark.django_db
    def test_product_name_required(self):
        form = ProductForm(data={"name": ""})
        assert not form.is_valid()
        assert "name" in form.errors

    @pytest.mark.django_db
    def test_product_name_strips_whitespace(self):
        form = ProductForm(data={"name": "  Widget  "})
        form.is_valid()
        assert form.cleaned_data["name"] == "Widget"


# ──────────────────────────────────────────────────────────────────────────────
# Product form cross-field rules
# ──────────────────────────────────────────────────────────────────────────────


class TestProductFormCrossField:
    @pytest.mark.django_db
    def test_catalogue_item_requires_sale_price(self):
        form = ProductForm(data={"name": "Cat Product", "catalogue_item": True})
        assert not form.is_valid()
        assert "catalogue_item" in form.errors

    @pytest.mark.django_db
    def test_catalogue_item_with_sale_price_valid(self):
        form = ProductForm(
            data={
                "name": "Cat Product",
                "catalogue_item": True,
                "sale_price": "19.99",
            }
        )
        assert form.is_valid()

    @pytest.mark.django_db
    def test_product_name_uniqueness(self):
        _product_with_deps("Existing Product")
        form = ProductForm(data={"name": "Existing Product"})
        assert not form.is_valid()
        assert "name" in form.errors

    @pytest.mark.django_db
    def test_product_name_case_insensitive_uniqueness(self):
        _product_with_deps("Unique Widget")
        form = ProductForm(data={"name": "unique widget"})
        assert not form.is_valid()
        assert "name" in form.errors

    @pytest.mark.django_db
    def test_product_name_uniqueness_excludes_self(self):
        product = _product_with_deps("Self Product")
        form = ProductForm(data={"name": "Self Product"}, instance=product)
        assert form.is_valid()


# ──────────────────────────────────────────────────────────────────────────────
# Quantity & price constraints
# ──────────────────────────────────────────────────────────────────────────────


class TestQuantityConstraints:
    @pytest.mark.django_db
    def test_sales_order_line_zero_qty(self):
        form = SalesOrderLineForm(data={"quantity": 0})
        form.is_valid()
        assert "quantity" in form.errors

    @pytest.mark.django_db
    def test_sales_order_line_negative_qty(self):
        form = SalesOrderLineForm(data={"quantity": -5})
        form.is_valid()
        assert "quantity" in form.errors

    @pytest.mark.django_db
    def test_purchase_order_line_zero_qty(self):
        form = PurchaseOrderLineForm(data={"quantity": 0})
        form.is_valid()
        assert "quantity" in form.errors

    @pytest.mark.django_db
    def test_production_form_zero_qty(self):
        form = ProductionForm(data={"quantity": 0})
        form.is_valid()
        assert "quantity" in form.errors

    @pytest.mark.django_db
    def test_bom_item_zero_qty(self):
        from production.models import BillOfMaterials

        parent = _product_with_deps("bom_parent")
        comp = _product_with_deps("bom_comp")
        bom = BillOfMaterials.objects.create(product=parent)
        form = BOMItemForm(data={"bom": bom.pk, "product": comp.pk, "quantity": 0})
        form.is_valid()
        assert "quantity" in form.errors

    @pytest.mark.django_db
    def test_inventory_adjust_zero_qty(self):
        """InventoryAdjustForm.clean_quantity rejects zero."""
        from django.core.exceptions import ValidationError

        product = _product_with_deps("adj_prod")
        form = InventoryAdjustForm(data={"product": product.pk, "quantity": 0})
        form.is_bound = True
        form.cleaned_data = {"quantity": 0}
        with pytest.raises(ValidationError):
            form.clean_quantity()


class TestPriceConstraints:
    @pytest.mark.django_db
    def test_customer_product_zero_price(self):
        customer = Customer.objects.create(name="Price_Cust")
        product = _product_with_deps("Price_Prod")
        form = CustomerProductForm(
            data={"customer": customer.pk, "product": product.pk, "price": "0"}
        )
        assert not form.is_valid()
        assert "price" in form.errors

    @pytest.mark.django_db
    def test_customer_product_negative_price(self):
        customer = Customer.objects.create(name="Neg_Cust")
        product = _product_with_deps("Neg_Prod")
        form = CustomerProductForm(
            data={"customer": customer.pk, "product": product.pk, "price": "-5.00"}
        )
        assert not form.is_valid()
        assert "price" in form.errors

    @pytest.mark.django_db
    def test_supplier_product_zero_cost(self):
        supplier = Supplier.objects.create(name="Cost_Sup")
        product = _product_with_deps("Cost_Prod")
        form = SupplierProductForm(
            data={
                "supplier": supplier.pk,
                "product": product.pk,
                "cost": "0",
            }
        )
        assert not form.is_valid()
        assert "cost" in form.errors

    @pytest.mark.django_db
    def test_supplier_product_negative_cost(self):
        supplier = Supplier.objects.create(name="NegCost_Sup")
        product = _product_with_deps("NegCost_Prod")
        form = SupplierProductForm(
            data={
                "supplier": supplier.pk,
                "product": product.pk,
                "cost": "-10",
            }
        )
        assert not form.is_valid()
        assert "cost" in form.errors

    @pytest.mark.django_db
    def test_supplier_product_valid_cost(self):
        supplier = Supplier.objects.create(name="ValidCost_Sup")
        product = _product_with_deps("ValidCost_Prod")
        form = SupplierProductForm(
            data={
                "supplier": supplier.pk,
                "product": product.pk,
                "cost": "10.50",
            }
        )
        assert form.is_valid()


# ──────────────────────────────────────────────────────────────────────────────
# Supplier product duplicate check
# ──────────────────────────────────────────────────────────────────────────────


class TestSupplierProductDuplicate:
    @pytest.mark.django_db
    def test_duplicate_supplier_product_rejected(self):
        supplier = Supplier.objects.create(name="Dup_Supplier")
        product = _product_with_deps("Dup_Product")
        SupplierProduct.objects.create(
            supplier=supplier, product=product, cost=Decimal("10.00")
        )

        form = SupplierProductForm(
            data={
                "supplier": supplier.pk,
                "product": product.pk,
                "cost": "15.00",
            }
        )
        assert not form.is_valid()


# ──────────────────────────────────────────────────────────────────────────────
# Config forms
# ──────────────────────────────────────────────────────────────────────────────


class TestCompanyConfigForm:
    @pytest.mark.django_db
    def test_valid_config(self):
        form = CompanyConfigForm(data={"name": "My Company"})
        assert form.is_valid()

    @pytest.mark.django_db
    def test_name_required(self):
        form = CompanyConfigForm(data={"name": ""})
        assert not form.is_valid()
        assert "name" in form.errors


class TestCompletePairingForm:
    def test_valid_api_key(self):
        form = CompletePairingForm(data={"api_key": "abc123"})
        assert form.is_valid()

    def test_empty_api_key(self):
        form = CompletePairingForm(data={"api_key": ""})
        assert not form.is_valid()
        assert "api_key" in form.errors

    def test_whitespace_api_key(self):
        form = CompletePairingForm(data={"api_key": "   "})
        assert not form.is_valid()
        assert "api_key" in form.errors
