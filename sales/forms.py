from django import forms
from django.core.validators import EmailValidator, RegexValidator

from .models import (
    Customer,
    CustomerContact,
    CustomerProduct,
    SalesOrder,
    SalesOrderLine,
)

# ── shared validators ──────────────────────────────────────────────────

phone_validator = RegexValidator(
    regex=r"^\+?[\d\s\-().]{7,64}$",
    message="Enter a valid phone number (digits, spaces, dashes, parentheses).",
)

ADDRESS_FIELDS = [
    "address_line_1",
    "address_line_2",
    "city",
    "state",
    "postal_code",
    "country",
]


# ── Customer ───────────────────────────────────────────────────────────


class CustomerForm(forms.ModelForm):
    email = forms.CharField(
        max_length=128,
        required=False,
        validators=[EmailValidator()],
        help_text="Optional email address.",
    )
    phone = forms.CharField(
        max_length=64,
        required=False,
        validators=[phone_validator],
        help_text="Optional phone number.",
    )
    website = forms.URLField(
        max_length=256,
        required=False,
        help_text="Full URL including https://",
    )

    class Meta:
        model = Customer
        fields = ["name", "phone", "email", "website"] + ADDRESS_FIELDS

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Customer name is required.")
        return name


# ── Customer Contact ───────────────────────────────────────────────────


class CustomerContactForm(forms.ModelForm):
    email = forms.CharField(
        max_length=128,
        required=False,
        validators=[EmailValidator()],
        help_text="Optional email address.",
    )
    phone = forms.CharField(
        max_length=64,
        required=False,
        validators=[phone_validator],
        help_text="Digits, spaces, dashes and parentheses accepted.",
    )

    class Meta:
        model = CustomerContact
        fields = ["customer", "name", "phone", "email"] + ADDRESS_FIELDS

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Contact name is required.")
        return name


# ── Customer Product ───────────────────────────────────────────────────


class CustomerProductForm(forms.ModelForm):
    class Meta:
        model = CustomerProduct
        fields = ["customer", "product", "price"]
        help_texts = {
            "price": "Selling price for this customer (must be greater than zero).",
        }
        widgets = {
            "price": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
        }

    def clean_price(self):
        price = self.cleaned_data["price"]
        if price is not None and price <= 0:
            raise forms.ValidationError("Price must be greater than zero.")
        return price


# ── Sales Order ────────────────────────────────────────────────────────


class SalesOrderForm(forms.ModelForm):
    class Meta:
        model = SalesOrder
        fields = ["customer", "ship_by_date"]
        widgets = {
            "ship_by_date": forms.DateInput(attrs={"type": "date"}),
        }
        help_texts = {
            "ship_by_date": "Target date to ship this order by.",
        }


class SalesOrderLineForm(forms.ModelForm):
    class Meta:
        model = SalesOrderLine
        fields = ["product", "quantity"]
        help_texts = {
            "quantity": "Number of units to include (must be at least 1).",
        }

    def clean_quantity(self):
        qty = self.cleaned_data.get("quantity")
        if qty is not None and qty <= 0:
            raise forms.ValidationError("Quantity must be at least 1.")
        return qty
