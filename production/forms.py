from django import forms
from .models import BillOfMaterials, BOMItem, Production


class BillOfMaterialsForm(forms.ModelForm):
    class Meta:
        model = BillOfMaterials
        fields = ["product"]


class BOMItemForm(forms.ModelForm):
    class Meta:
        model = BOMItem
        fields = ["bom", "product", "quantity"]

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

    def clean_quantity(self):
        qty = self.cleaned_data.get("quantity")
        if qty is not None and qty <= 0:
            raise forms.ValidationError("Quantity must be at least 1.")
        return qty
