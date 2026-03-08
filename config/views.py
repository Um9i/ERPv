import httpx
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, CreateView, DeleteView
from django.views.generic.edit import UpdateView

from .forms import CompanyConfigForm, CompletePairingForm, PairedInstanceForm
from .models import CompanyConfig, PairedInstance

_IMPORT_FIELDS = [
    "name",
    "phone",
    "email",
    "website",
    "address_line_1",
    "address_line_2",
    "city",
    "state",
    "postal_code",
    "country",
]


class CompanyConfigView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = CompanyConfig
    form_class = CompanyConfigForm
    template_name = "config/company_config.html"
    success_url = reverse_lazy("config:company-config")

    def test_func(self):
        return self.request.user.is_staff

    def get_object(self, queryset=None):
        obj, _ = CompanyConfig.objects.get_or_create(pk=1, defaults={"name": "ERPv"})
        return obj

    def form_valid(self, form):
        messages.success(self.request, "Company configuration saved.")
        return super().form_valid(form)


@method_decorator(csrf_exempt, name="dispatch")
class CompanyApiView(View):
    """Machine-to-machine endpoint — returns company info to paired instances."""

    def get(self, request, *args, **kwargs):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer "):
            return JsonResponse({"error": "Unauthorized"}, status=401)
        key = auth[len("Bearer ") :]
        if not PairedInstance.objects.filter(our_key=key).exists():
            return JsonResponse({"error": "Unauthorized"}, status=401)
        company = CompanyConfig.get_or_default()
        return JsonResponse(
            {
                "name": company.name,
                "address_line_1": company.address_line_1,
                "address_line_2": company.address_line_2,
                "city": company.city,
                "state": company.state,
                "postal_code": company.postal_code,
                "country": company.country,
                "phone": company.phone,
                "email": company.email,
                "website": company.website,
                "vat_number": company.vat_number,
                "company_number": company.company_number,
            }
        )


class PairedInstanceListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = PairedInstance
    template_name = "config/paired_instance_list.html"
    context_object_name = "instances"

    def test_func(self):
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["new_our_key"] = self.request.session.pop("new_paired_key", None)
        return ctx


class PairedInstanceCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = PairedInstance
    form_class = PairedInstanceForm
    template_name = "config/paired_instance_form.html"
    success_url = reverse_lazy("config:paired-instance-list")

    def test_func(self):
        return self.request.user.is_staff

    def form_valid(self, form):
        response = super().form_valid(form)
        # Store the key in the session so it can be displayed once on the list page.
        self.request.session["new_paired_key"] = self.object.our_key
        messages.success(
            self.request, f'Paired instance "{self.object.name}" created successfully.'
        )
        return response


class PairedInstanceDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = PairedInstance
    template_name = "config/paired_instance_delete.html"
    success_url = reverse_lazy("config:paired-instance-list")

    def test_func(self):
        return self.request.user.is_staff


class PairedInstanceCompleteView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Phase 2 — enter the remote api_key once the partner has shared it."""

    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, pk, *args, **kwargs):
        instance = get_object_or_404(PairedInstance, pk=pk)
        form = CompletePairingForm()
        return self._render(request, instance, form)

    def post(self, request, pk, *args, **kwargs):
        instance = get_object_or_404(PairedInstance, pk=pk)
        form = CompletePairingForm(request.POST)
        if form.is_valid():
            instance.api_key = form.cleaned_data["api_key"]
            instance.save()
            messages.success(
                request, f'Pairing with "{instance.name}" is now complete.'
            )
            return redirect(reverse_lazy("config:paired-instance-list"))
        return self._render(request, instance, form)

    def _render(self, request, instance, form):
        from django.shortcuts import render

        return render(
            request,
            "config/paired_instance_complete.html",
            {
                "instance": instance,
                "form": form,
            },
        )


class ImportAsCustomerView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Fetch remote company data and redirect to Customer create form pre-filled."""

    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, pk, *args, **kwargs):
        instance = get_object_or_404(PairedInstance, pk=pk)
        if not instance.api_key:
            messages.error(
                request, "Pairing is not complete \u2014 enter their API key first."
            )
            return redirect(reverse_lazy("config:paired-instance-list"))
        try:
            resp = httpx.get(
                f"{instance.url.rstrip('/')}/config/api/company/",
                headers={"Authorization": f"Bearer {instance.api_key}"},
                timeout=5.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            messages.error(request, f"Could not fetch data from {instance.name}: {exc}")
            return redirect(reverse_lazy("config:paired-instance-list"))
        params = {f: data.get(f, "") for f in _IMPORT_FIELDS}
        return redirect(f"{reverse_lazy('sales:customer-create')}?{urlencode(params)}")


class ImportAsSupplierView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Fetch remote company data and redirect to Supplier create form pre-filled."""

    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, pk, *args, **kwargs):
        instance = get_object_or_404(PairedInstance, pk=pk)
        if not instance.api_key:
            messages.error(
                request, "Pairing is not complete \u2014 enter their API key first."
            )
            return redirect(reverse_lazy("config:paired-instance-list"))
        try:
            resp = httpx.get(
                f"{instance.url.rstrip('/')}/config/api/company/",
                headers={"Authorization": f"Bearer {instance.api_key}"},
                timeout=5.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            messages.error(request, f"Could not fetch data from {instance.name}: {exc}")
            return redirect(reverse_lazy("config:paired-instance-list"))
        params = {f: data.get(f, "") for f in _IMPORT_FIELDS}
        return redirect(
            f"{reverse_lazy('procurement:supplier-create')}?{urlencode(params)}"
        )
