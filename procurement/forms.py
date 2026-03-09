from django import forms
from django.core.validators import EmailValidator, RegexValidator
from .models import (
    Supplier,
    SupplierContact,
    SupplierProduct,
    PurchaseOrder,
    PurchaseOrderLine,
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
    )
    phone = forms.CharField(
        max_length=64,
        required=False,
        validators=[phone_validator],
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


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ["supplier", "due_date"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }


class PurchaseOrderLineForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrderLine
        fields = ["product", "quantity"]

    def clean_quantity(self):
        qty = self.cleaned_data.get("quantity")
        if qty is not None and qty <= 0:
            raise forms.ValidationError("Quantity must be at least 1.")
        return qty
