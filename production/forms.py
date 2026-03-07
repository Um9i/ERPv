from django import forms
from .models import BillOfMaterials, BOMItem, Production
from inventory.models import Location


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
