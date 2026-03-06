from django import forms
from .models import Product, InventoryAdjust


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Product name is required.")
        # check uniqueness explicitly so the error message is clearer
        qs = Product.objects.filter(name__iexact=name)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'A product named "{name}" already exists.')
        return name


class InventoryAdjustForm(forms.ModelForm):
    class Meta:
        model = InventoryAdjust
        fields = ["product", "quantity"]

    def clean_quantity(self):
        qty = self.cleaned_data.get("quantity")
        if qty is not None and qty == 0:
            raise forms.ValidationError("Adjustment quantity cannot be zero.")
        return qty
