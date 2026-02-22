from .models import (
    BillOfMaterials,
    BOMItem,
    Production,
)
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
    TemplateView,
)
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django import forms
from django.db.models import F
from django.http import JsonResponse


# ----- BOM views -----

class BOMCreateView(CreateView):
    model = BillOfMaterials
    template_name = "production/bom_form.html"
    fields = ["product"]
    success_url = reverse_lazy("production:bom-list")


class BOMUpdateView(UpdateView):
    model = BillOfMaterials
    template_name = "production/bom_form.html"
    fields = ["product"]
    success_url = reverse_lazy("production:bom-list")


class BOMDeleteView(DeleteView):
    model = BillOfMaterials
    template_name = "production/bom_confirm_delete.html"
    success_url = reverse_lazy("production:bom-list")


class BOMListView(ListView):
    model = BillOfMaterials
    template_name = "production/bom_list.html"
    context_object_name = "boms"

    def get_queryset(self):
        qs = BillOfMaterials.objects.all().select_related("product")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(product__name__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        from django.core.paginator import Paginator

        context = super().get_context_data(**kwargs)
        boms = self.get_queryset()
        page = self.request.GET.get("page")
        paginator = Paginator(boms, 20)
        context["boms"] = paginator.get_page(page)
        context["q"] = self.request.GET.get("q", "")
        return context


class BOMDetailView(DetailView):
    model = BillOfMaterials
    template_name = "production/bom_detail.html"
    context_object_name = "bom"

    def get_context_data(self, **kwargs):
        from django.core.paginator import Paginator

        context = super().get_context_data(**kwargs)
        bom = self.object
        items = bom.bom_items.select_related("product").all()
        page = self.request.GET.get("page")
        paginator = Paginator(items, 10)
        context["bom_items"] = paginator.get_page(page)
        return context


class BOMItemCreateView(CreateView):
    model = BOMItem
    template_name = "production/bom_item_form.html"
    fields = ["bom", "product", "quantity"]
    success_url = reverse_lazy("production:bom-list")

    def get_initial(self):
        initial = super().get_initial()
        bom_id = self.request.GET.get("bom")
        if bom_id:
            initial["bom"] = bom_id
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        bom_id = self.request.GET.get("bom")
        if bom_id:
            form.fields["bom"].widget = forms.HiddenInput()
        return form

    def get_success_url(self):
        return reverse_lazy("production:bom-detail", args=[self.object.bom.pk])


class BOMItemUpdateView(UpdateView):
    model = BOMItem
    template_name = "production/bom_item_form.html"
    fields = ["bom", "product", "quantity"]

    def get_success_url(self):
        return reverse_lazy("production:bom-detail", args=[self.object.bom.pk])


class BOMItemDeleteView(DeleteView):
    model = BOMItem
    template_name = "production/bom_item_confirm_delete.html"

    def get_success_url(self):
        return reverse_lazy("production:bom-detail", args=[self.object.bom.pk])


# ----- Production job views -----

class ProductionCreateView(CreateView):
    model = Production
    template_name = "production/production_form.html"
    # do not expose the `complete` checkbox when creating; jobs are always
    # started in an open state.  the update view still allows toggling it.
    fields = ["product", "quantity"]
    success_url = reverse_lazy("production:production-list")

    def get_initial(self):
        initial = super().get_initial()
        product_id = self.request.GET.get("product")
        if product_id:
            initial["product"] = product_id
        qty = self.request.GET.get("quantity")
        if qty:
            try:
                # allow numeric value or string
                initial["quantity"] = int(qty)
            except ValueError:
                initial["quantity"] = qty
        return initial

    def get_form(self, form_class=None):
        # only allow selection of products that actually have a bill of materials
        form = super().get_form(form_class)
        from inventory.models import Product

        form.fields["product"].queryset = Product.objects.filter(
            billofmaterials__isnull=False
        )
        return form

    def form_valid(self, form):
        # ensure bom allocated happens in model save
        return super().form_valid(form)


class ProductionUpdateView(UpdateView):
    model = Production
    template_name = "production/production_form.html"
    fields = ["product", "quantity", "complete"]
    success_url = reverse_lazy("production:production-list")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        from inventory.models import Product

        # include only products that have a BOM; also allow the current
        # product in case its BOM was removed after creation.
        qs = Product.objects.filter(billofmaterials__isnull=False)
        if self.object and self.object.product_id not in qs.values_list("id", flat=True):
            qs = qs | Product.objects.filter(pk=self.object.product_id)
        form.fields["product"].queryset = qs
        return form


class ProductionListView(ListView):
    model = Production
    template_name = "production/production_list.html"
    context_object_name = "productions"

    def get_queryset(self):
        qs = Production.objects.all().order_by("-created_at")
        q = self.request.GET.get("q", "").strip()
        if q:
            from django.db.models import Q

            qs = qs.filter(Q(product__name__icontains=q) | Q(pk__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        from django.core.paginator import Paginator

        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        page = self.request.GET.get("page")
        paginator = Paginator(qs, 15)
        context["productions"] = paginator.get_page(page)
        context["q"] = self.request.GET.get("q", "")
        return context


class ProductionListApiView(TemplateView):
    def get(self, request, *args, **kwargs):
        qs = Production.objects.all().order_by("-created_at").filter(complete=False)
        q = self.request.GET.get("q", "").strip()
        if q:
            from django.db.models import Q

            qs = qs.filter(Q(product__name__icontains=q) | Q(pk__icontains=q))
        data = []
        for prod in qs:
            data.append(
                {
                    "id": prod.id,
                    "product": prod.product.name,
                    "quantity": prod.quantity,
                    "quantity_received": prod.quantity_received,
                    "complete": prod.complete,
                    "closed": prod.closed,
                    "created_at": prod.created_at.isoformat(),
                }
            )
        return JsonResponse({"productions": data})


class ProductionDetailView(DetailView):
    model = Production
    template_name = "production/production_detail.html"
    context_object_name = "production"

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if "complete_production" in request.POST:
            self.object.complete = True
            self.object.save()
            return redirect(request.path)
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        production = self.object
        context["bom"] = production.bom()
        return context


class ProductionReceivingListView(ListView):
    model = Production
    template_name = "production/production_receiving_list.html"
    context_object_name = "productions"

    def get_queryset(self):
        # show only jobs that have not yet been marked complete
        qs = Production.objects.filter(complete=False).order_by("-created_at")
        q = self.request.GET.get("q", "").strip()
        if q:
            from django.db.models import Q

            qs = qs.filter(Q(product__name__icontains=q) | Q(pk__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        from django.core.paginator import Paginator

        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        page = self.request.GET.get("page")
        paginator = Paginator(qs, 15)
        context["productions"] = paginator.get_page(page)
        context["q"] = self.request.GET.get("q", "")
        return context


class ProductionReceiveView(DetailView):
    model = Production
    template_name = "production/production_receive.html"
    context_object_name = "production"

    def post(self, request, *args, **kwargs):
        # handle receiving of a specified quantity (or all remaining)
        from django.contrib import messages

        self.object = self.get_object()
        received = 0
        if "receive_all" in request.POST:
            received = self.object.remaining
        else:
            try:
                received = int(request.POST.get("received", 0))
            except (TypeError, ValueError):
                received = 0
            # sanitize input: cannot be negative or exceed remaining
            if received < 0:
                received = 0
            if received > self.object.remaining:
                received = self.object.remaining
        if received > 0:
            self.object.quantity_received = self.object.quantity_received + received
            try:
                self.object.save()
            except Exception as e:
                # swallow validation error and inform user
                messages.error(request, str(e))
                return redirect(request.path)
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy("production:production-receiving-list")


class ProductionDashboardView(TemplateView):
    template_name = "production/production_dashboard.html"

    def get_context_data(self, **kwargs):
        from django.db.models import Count

        context = super().get_context_data(**kwargs)
        context["total_boms"] = BillOfMaterials.objects.count()
        context["active_jobs"] = Production.objects.filter(closed=False).count()
        context["completed_jobs"] = Production.objects.filter(complete=True).count()
        return context
