from django import forms
from django.db import models
from .models import Product, InventoryAdjust, Location, InventoryLocation, StockTransfer


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "description", "image", "sale_price"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }

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
    location = forms.ModelChoiceField(
        queryset=Location.objects.none(),
        required=False,
        empty_label="— No specific location —",
    )

    class Meta:
        model = InventoryAdjust
        fields = ["product", "quantity"]

    def __init__(self, *args, inventory=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.inventory = inventory
        if inventory:
            assigned_location_ids = inventory.stock_locations.values_list(
                "location_id", flat=True
            )
            self.fields["location"].queryset = Location.objects.filter(
                pk__in=assigned_location_ids
            )
            if not assigned_location_ids.exists():
                self.fields["location"].widget = forms.HiddenInput()

    def clean_quantity(self):
        qty = self.cleaned_data.get("quantity")
        if qty is not None and qty == 0:
            raise forms.ValidationError("Adjustment quantity cannot be zero.")
        return qty

    def clean(self):
        cleaned = super().clean()
        qty = cleaned.get("quantity")
        location = cleaned.get("location")
        if location and qty and qty < 0 and self.inventory:
            try:
                inv_loc = InventoryLocation.objects.get(
                    inventory=self.inventory,
                    location=location,
                )
                if inv_loc.quantity + qty < 0:
                    raise forms.ValidationError(
                        f"Only {inv_loc.quantity} units in "
                        f"{location} — cannot remove {abs(qty)}."
                    )
            except InventoryLocation.DoesNotExist:
                raise forms.ValidationError(f"No stock assigned to {location}.")
        return cleaned


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ["name", "parent"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].required = False
        self.fields["parent"].empty_label = "— None (top-level) —"
        if self.instance.pk:
            self.fields["parent"].queryset = Location.objects.exclude(
                pk=self.instance.pk
            )


class InventoryLocationForm(forms.ModelForm):
    class Meta:
        model = InventoryLocation
        fields = ["location", "quantity"]

    def __init__(self, *args, inventory=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.inventory = inventory
        self.fields["location"].queryset = Location.objects.all()
        self.fields["location"].empty_label = "Select a location\u2026"

    def clean(self):
        cleaned = super().clean()
        qty = cleaned.get("quantity")
        location = cleaned.get("location")
        if self.inventory is None:
            return cleaned
        qs = InventoryLocation.objects.filter(inventory=self.inventory)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        other_qty = qs.aggregate(total=models.Sum("quantity"))["total"] or 0
        total = other_qty + (qty or 0)
        if total > self.inventory.quantity:
            raise forms.ValidationError(
                f"Total allocated ({total}) would exceed stock on hand "
                f"({self.inventory.quantity}). Adjust stock first."
            )
        return cleaned


class StockTransferForm(forms.ModelForm):
    class Meta:
        model = StockTransfer
        fields = ["from_location", "to_location", "quantity", "note"]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, inventory=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.inventory = inventory
        # only show locations that have stock for this inventory
        if inventory:
            assigned_location_ids = InventoryLocation.objects.filter(
                inventory=inventory, quantity__gt=0
            ).values_list("location_id", flat=True)
            self.fields["from_location"].queryset = Location.objects.filter(
                pk__in=assigned_location_ids
            )
        self.fields["from_location"].empty_label = "Select source\u2026"
        self.fields["to_location"].queryset = Location.objects.all()
        self.fields["to_location"].empty_label = "Select destination\u2026"
