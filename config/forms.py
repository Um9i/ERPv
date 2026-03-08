from django import forms

from .models import CompanyConfig, PairedInstance


class CompanyConfigForm(forms.ModelForm):
    class Meta:
        model = CompanyConfig
        fields = [
            "name",
            "phone",
            "email",
            "website",
            "logo",
            "vat_number",
            "company_number",
            # AddressMixin fields
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "postal_code",
            "country",
        ]
        widgets = {
            f: forms.TextInput(attrs={"class": "form-control"})
            for f in [
                "name",
                "phone",
                "email",
                "website",
                "vat_number",
                "company_number",
                "address_line_1",
                "address_line_2",
                "city",
                "state",
                "postal_code",
                "country",
            ]
        }


class PairedInstanceForm(forms.ModelForm):
    class Meta:
        model = PairedInstance
        fields = ["name", "url", "api_key", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "url": forms.URLInput(attrs={"class": "form-control"}),
            "api_key": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }
