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
        help_texts = {
            "website": "Full URL including https://",
            "vat_number": "VAT / tax registration number (optional).",
            "company_number": "Company registration number (optional).",
        }


class PairedInstanceForm(forms.ModelForm):
    class Meta:
        model = PairedInstance
        fields = [
            "name",
            "url",
            "notes",
        ]  # supplier is set programmatically, not by user
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "url": forms.URLInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }
        help_texts = {
            "url": "Full URL of the remote instance, e.g. https://erp.example.com",
            "notes": "Optional notes about this paired instance.",
        }


class CompletePairingForm(forms.Form):
    api_key = forms.CharField(
        max_length=64,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control"}),
        label="Their API Key",
        help_text="The key the remote instance generated for you.",
    )

    def clean_api_key(self):
        key = self.cleaned_data["api_key"].strip()
        if not key:
            raise forms.ValidationError("API key is required.")
        return key
