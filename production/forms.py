from django import forms
from django.db.models import Q

from inventory.models import Location

from .models import BillOfMaterials, BOMItem, Production


class BillOfMaterialsForm(forms.ModelForm):
    class Meta:
        model = BillOfMaterials
        fields = ["product", "production_cost"]
        widgets = {
            "production_cost": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }
        help_texts = {
            "production_cost": "Additional cost to produce one unit (optional).",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["production_cost"].required = False


class BOMItemForm(forms.ModelForm):
    class Meta:
        model = BOMItem
        fields = ["bom", "product", "quantity"]
        help_texts = {
            "quantity": "Number of units required per production run.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show products that can be procured or produced.
        self.fields["product"].queryset = (
            self.fields["product"]
            .queryset.filter(
                Q(product_suppliers__isnull=False) | Q(billofmaterials__isnull=False)
            )
            .distinct()
        )

    def clean_quantity(self):
        qty = self.cleaned_data.get("quantity")
        if qty is not None and qty <= 0:
            raise forms.ValidationError("Quantity must be at least 1.")
        return qty


class ProductionForm(forms.ModelForm):
    class Meta:
        model = Production
        fields = ["product", "quantity", "due_date"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }
        help_texts = {
            "quantity": "Number of units to produce (must be at least 1).",
            "due_date": "Target completion date for this production run.",
        }

    def clean_quantity(self):
        qty = self.cleaned_data.get("quantity")
        if qty is not None and qty <= 0:
            raise forms.ValidationError("Quantity must be at least 1.")
        return qty


class ProductionUpdateForm(forms.ModelForm):
    """Separate form for updates that also exposes the ``complete`` toggle."""

    class Meta:
        model = Production
        fields = ["product", "quantity", "due_date", "complete"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }
        help_texts = {
            "quantity": "Number of units to produce (must be at least 1).",
            "due_date": "Target completion date for this production run.",
            "complete": "Tick to mark this production run as finished.",
        }

    def clean_quantity(self):
        qty = self.cleaned_data.get("quantity")
        if qty is not None and qty <= 0:
            raise forms.ValidationError("Quantity must be at least 1.")
        return qty


class ProductionReceiveForm(forms.Form):
    quantity_to_receive = forms.IntegerField(min_value=1)
    location = forms.ModelChoiceField(
        queryset=Location.objects.all(),
        required=False,
        empty_label="— No specific location —",
    )

    def __init__(self, *args, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance
        if instance:
            self.fields["quantity_to_receive"].initial = instance.remaining
            self.fields["quantity_to_receive"].widget.attrs["max"] = instance.remaining

    def clean_quantity_to_receive(self):
        qty = self.cleaned_data["quantity_to_receive"]
        if self.instance and qty > self.instance.remaining:
            raise forms.ValidationError(
                f"Only {self.instance.remaining} units remaining."
            )
        return qty
