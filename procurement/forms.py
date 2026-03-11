from django import forms
from django.core.validators import EmailValidator, RegexValidator

from .models import (
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierContact,
    SupplierProduct,
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


# ── Supplier ───────────────────────────────────────────────────────────


class SupplierForm(forms.ModelForm):
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
        model = Supplier
        fields = ["name", "phone", "email", "website"] + ADDRESS_FIELDS

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Supplier name is required.")
        return name


# ── Supplier Contact ──────────────────────────────────────────────────


class SupplierContactForm(forms.ModelForm):
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
        model = SupplierContact
        fields = ["supplier", "name", "phone", "email"] + ADDRESS_FIELDS

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Contact name is required.")
        return name


# ── Supplier Product ──────────────────────────────────────────────────


class SupplierProductForm(forms.ModelForm):
    class Meta:
        model = SupplierProduct
        fields = ["supplier", "product", "cost"]
        help_texts = {
            "cost": "Unit cost from this supplier (must be greater than zero).",
        }
        widgets = {
            "cost": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
        }

    def clean_cost(self):
        cost = self.cleaned_data["cost"]
        if cost is not None and cost <= 0:
            raise forms.ValidationError("Cost must be greater than zero.")
        return cost

    def validate_unique(self):
        """Provide a friendlier duplicate‑product message."""
        try:
            super().validate_unique()
        except forms.ValidationError:
            raise forms.ValidationError(
                "This supplier already carries the selected product."
            )


# ── Purchase Order ────────────────────────────────────────────────────


class RequiredPOLineFormSet(forms.BaseInlineFormSet):
    """Inline formset that requires at least one line item."""

    default_error_messages = {
        "too_few_forms": "A purchase order must have at least one line item.",
    }


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ["supplier", "due_date"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }
        help_texts = {
            "due_date": "Expected delivery date for this order.",
        }


class PurchaseOrderLineForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrderLine
        fields = ["product", "quantity"]
        help_texts = {
            "quantity": "Number of units to order (must be at least 1).",
        }

    def clean_quantity(self):
        qty = self.cleaned_data.get("quantity")
        if qty is not None and qty <= 0:
            raise forms.ValidationError("Quantity must be at least 1.")
        return qty
