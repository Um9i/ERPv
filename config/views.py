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
from .notifications import _notify_remote_customer, _notify_remote_customer_product

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
        remote_name = data.get("name", "").strip()

        if remote_name:
            from sales.models import Customer as _Customer

            existing = _Customer.objects.filter(name__iexact=remote_name).first()
            if existing and not instance.customer:
                instance.customer = existing
                instance.save(update_fields=["customer"])
                messages.success(
                    request,
                    f'Linked existing customer "{existing.name}" to {instance.name}.',
                )
                return redirect(reverse_lazy("config:paired-instance-list"))

        self.request.session["link_customer_to_paired"] = pk
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
        remote_name = data.get("name", "").strip()

        # If a supplier with this name already exists, link it directly without
        # redirecting to the create form (avoids UniqueConstraint violation).
        if remote_name:
            from procurement.models import Supplier as _Supplier

            existing = _Supplier.objects.filter(name__iexact=remote_name).first()
            if existing and not instance.supplier:
                instance.supplier = existing
                instance.save(update_fields=["supplier"])
                messages.success(
                    request,
                    f'Linked existing supplier "{existing.name}" to {instance.name}.',
                )
                if not _notify_remote_customer(instance):
                    messages.warning(
                        request,
                        f"Could not notify {instance.name} of customer link — check connectivity.",
                    )
                return redirect(
                    reverse_lazy(
                        "config:paired-instance-browse-catalogue", kwargs={"pk": pk}
                    )
                )

        self.request.session["link_supplier_to_paired"] = pk
        return redirect(
            f"{reverse_lazy('procurement:supplier-create')}?{urlencode(params)}"
        )


class ImportCatalogueProductView(LoginRequiredMixin, UserPassesTestMixin, View):
    """POST-only: import a remote catalogue item as a local Product + SupplierProduct."""

    def test_func(self):
        return self.request.user.is_staff

    def post(self, request, pk, *args, **kwargs):
        from decimal import Decimal, InvalidOperation

        from procurement.models import Supplier, SupplierProduct
        from inventory.models import Product

        instance = get_object_or_404(PairedInstance, pk=pk)
        browse_url = reverse_lazy(
            "config:paired-instance-browse-catalogue", kwargs={"pk": pk}
        )

        if instance.status == "pending":
            messages.error(request, f'"{instance.name}" is not yet active.')
            return redirect(reverse_lazy("config:paired-instance-list"))

        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        sale_price_raw = request.POST.get("sale_price", "").strip()
        supplier_id = request.POST.get("supplier_id", "").strip()

        if not name or not supplier_id:
            messages.error(request, "Missing required fields (name or supplier_id).")
            return redirect(browse_url)

        try:
            cost = Decimal(sale_price_raw)
        except InvalidOperation:
            messages.error(request, f"Invalid sale price: {sale_price_raw!r}")
            return redirect(browse_url)

        try:
            supplier = Supplier.objects.get(pk=int(supplier_id))
        except (Supplier.DoesNotExist, ValueError):
            messages.error(request, f"Supplier with id {supplier_id!r} not found.")
            return redirect(browse_url)

        existing = Product.objects.filter(name__iexact=name).first()
        if existing:
            product = existing
        else:
            product = Product.objects.create(
                name=name,
                description=description,
                sale_price=cost,
                catalogue_item=False,
            )

        supplier_product, created = SupplierProduct.objects.get_or_create(
            supplier=supplier,
            product=product,
            defaults={"cost": cost},
        )
        if not created:
            supplier_product.cost = cost
            supplier_product.save(update_fields=["cost"])

        messages.success(
            request,
            f"Imported {product.name} as supplier product for {supplier.name}.",
        )
        if not _notify_remote_customer_product(instance, product.name, cost):
            messages.warning(
                request,
                f"Could not notify {instance.name} of product link — check connectivity.",
            )
        return redirect(browse_url)


@method_decorator(csrf_exempt, name="dispatch")
class NotifyCustomerView(View):
    """Inbound: remote tells us to create/link them as a Customer here."""

    def post(self, request, *args, **kwargs):
        import json

        from sales.models import Customer

        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer "):
            return JsonResponse({"error": "Unauthorized"}, status=401)
        key = auth[len("Bearer ") :]
        try:
            paired_instance = PairedInstance.objects.get(our_key=key)
        except PairedInstance.DoesNotExist:
            return JsonResponse({"error": "Unauthorized"}, status=401)

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        name = (data.get("name") or "").strip()
        if not name:
            return JsonResponse({"error": "name is required"}, status=400)

        existing = Customer.objects.filter(name__iexact=name).first()
        if existing:
            customer = existing
            created = False
        else:
            customer = Customer.objects.create(
                name=name,
                address_line_1=data.get("address_line_1", ""),
                address_line_2=data.get("address_line_2", ""),
                city=data.get("city", ""),
                state=data.get("state", ""),
                postal_code=data.get("postal_code", ""),
                country=data.get("country", ""),
                phone=data.get("phone", ""),
                email=data.get("email", ""),
                website=data.get("website", ""),
            )
            created = True

        paired_instance.customer = customer
        paired_instance.save(update_fields=["customer"])
        return JsonResponse({"status": "ok", "created": created})


@method_decorator(csrf_exempt, name="dispatch")
class NotifyCustomerProductView(View):
    """Inbound: remote tells us to create/link a CustomerProduct here."""

    def post(self, request, *args, **kwargs):
        import json
        from decimal import Decimal, InvalidOperation

        from sales.models import CustomerProduct
        from inventory.models import Product

        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer "):
            return JsonResponse({"error": "Unauthorized"}, status=401)
        key = auth[len("Bearer ") :]
        try:
            paired_instance = PairedInstance.objects.get(our_key=key)
        except PairedInstance.DoesNotExist:
            return JsonResponse({"error": "Unauthorized"}, status=401)

        if not paired_instance.customer:
            return JsonResponse(
                {"error": "Customer not linked to this paired instance"}, status=400
            )

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        product_name = (data.get("product_name") or "").strip()
        price_raw = str(data.get("price", "")).strip()

        product = Product.objects.filter(name__iexact=product_name).first()
        if not product:
            return JsonResponse({"error": "Product not found"}, status=400)

        try:
            price = Decimal(price_raw)
        except InvalidOperation:
            return JsonResponse({"error": f"Invalid price: {price_raw!r}"}, status=400)

        cp, created = CustomerProduct.objects.get_or_create(
            customer=paired_instance.customer,
            product=product,
            defaults={"price": price},
        )
        if not created:
            cp.price = price
            cp.save(update_fields=["price"])

        return JsonResponse({"status": "ok", "created": created})


class BrowseCatalogueView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Fetch and display the remote catalogue from a paired instance."""

    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, pk, *args, **kwargs):
        from django.shortcuts import render

        instance = get_object_or_404(PairedInstance, pk=pk)
        if instance.status == "pending":
            messages.error(
                request,
                f'"{instance.name}" is not yet active \u2014 enter their API key first.',
            )
            return redirect(reverse_lazy("config:paired-instance-list"))
        catalogue = None
        error = None
        try:
            resp = httpx.get(
                f"{instance.url.rstrip('/')}/inventory/api/catalogue/",
                headers={"Authorization": f"Bearer {instance.api_key}"},
                timeout=5.0,
            )
            if resp.status_code != 200:
                error = f"Remote server returned {resp.status_code}."
            else:
                catalogue = resp.json()
        except httpx.TimeoutException:
            error = f"Request to {instance.name} timed out."
        except Exception as exc:
            error = f"Could not fetch catalogue from {instance.name}: {exc}"

        if catalogue and instance.supplier:
            from procurement.models import SupplierProduct as _SP

            imported_names = set(
                name.lower()
                for name in _SP.objects.filter(supplier=instance.supplier).values_list(
                    "product__name", flat=True
                )
            )
            for item in catalogue:
                item["already_imported"] = item["name"].lower() in imported_names

        return render(
            request,
            "config/paired_instance_catalogue.html",
            {
                "instance": instance,
                "catalogue": catalogue,
                "error": error,
                "supplier": instance.supplier,
            },
        )
