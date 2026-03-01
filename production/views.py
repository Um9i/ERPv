from .models import (
    BillOfMaterials,
    BOMItem,
    Production,
)
from .forms import (
    BillOfMaterialsForm,
    BOMItemForm,
    ProductionForm,
    ProductionUpdateForm,
)
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
    TemplateView,
)
from django.forms.models import inlineformset_factory
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django import forms
from django.db.models import F, Q
from django.http import JsonResponse


# ----- BOM views -----

class BOMCreateView(CreateView):
    model = BillOfMaterials
    template_name = "production/bom_form.html"
    form_class = BillOfMaterialsForm
    # we'll redirect to the detail once created

    def get_success_url(self):
        return reverse_lazy("production:bom-detail", args=[self.object.pk])

    def get_initial(self):
        # allow preselecting product via GET as before
        initial = super().get_initial()
        product_id = self.request.GET.get("product")
        if product_id:
            initial["product"] = product_id
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        product_id = self.request.GET.get("product")
        if product_id:
            form.fields["product"].widget = forms.HiddenInput()
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # inline formset for BOM items
        LineFormset = inlineformset_factory(
            BillOfMaterials,
            BOMItem,
            form=BOMItemForm,
            extra=1,
            can_delete=True,
        )
        if self.request.POST:
            parent = None
            if "form" in kwargs:
                parent = kwargs["form"].instance
            if parent is None:
                parent = BillOfMaterials()
            context["lines_formset"] = LineFormset(self.request.POST, instance=parent)
        else:
            context["lines_formset"] = LineFormset()
        # hide DELETE checkboxes — JS remove buttons handle this
        for f in context["lines_formset"]:
            if "DELETE" in f.fields:
                f.fields["DELETE"].widget = forms.HiddenInput()
        return context

    def form_valid(self, form):
        # build an unsaved BOM instance so that the inline forms have access to
        # its `product` value during validation.  similar to the standard
        # pattern used elsewhere, but we avoid saving the parent until the
        # lines are confirmed valid to prevent orphan BOMs on error.
        context = self.get_context_data(form=form)
        lines_formset = context.get("lines_formset")
        # create instance without committing to DB yet
        self.object = form.save(commit=False)
        # bind the formset to this (unsaved) instance for validation
        lines_formset.instance = self.object
        if lines_formset.is_valid():
            # now that both parent and children are valid we can persist
            self.object.save()
            lines_formset.save()
            return super().form_valid(form)
        else:
            return self.form_invalid(form)


class BOMUpdateView(UpdateView):
    model = BillOfMaterials
    template_name = "production/bom_form.html"
    form_class = BillOfMaterialsForm

    def get_success_url(self):
        return reverse_lazy("production:bom-detail", args=[self.object.pk])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        LineFormset = inlineformset_factory(
            BillOfMaterials,
            BOMItem,
            form=BOMItemForm,
            extra=1,
            can_delete=True,
        )
        if self.request.POST:
            context["lines_formset"] = LineFormset(self.request.POST, instance=self.object)
        else:
            context["lines_formset"] = LineFormset(instance=self.object)
        # hide DELETE checkboxes — JS remove buttons handle this
        for f in context["lines_formset"]:
            if "DELETE" in f.fields:
                f.fields["DELETE"].widget = forms.HiddenInput()
        return context

    def form_valid(self, form):
        context = self.get_context_data(form=form)
        lines_formset = context.get("lines_formset")
        if lines_formset.is_valid():
            self.object = form.save()
            lines_formset.instance = self.object
            lines_formset.save()
            return super().form_valid(form)
        else:
            return self.form_invalid(form)


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
    form_class = BOMItemForm
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
    form_class = BOMItemForm

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
    form_class = ProductionForm
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
    form_class = ProductionUpdateForm
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
        qs = Production.objects.all().order_by("-created_at").select_related("product")
        status = self.request.GET.get("status", "").lower()
        if status == "active":
            qs = qs.filter(closed=False)
        elif status == "completed":
            qs = qs.filter(complete=True)
        q = self.request.GET.get("q", "").strip()
        if q:
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
        context["status"] = self.request.GET.get("status", "").lower()
        return context


class ProductionListApiView(TemplateView):
    def get(self, request, *args, **kwargs):
        qs = Production.objects.all().order_by("-created_at").filter(complete=False)
        q = self.request.GET.get("q", "").strip()
        if q:
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
        if "cancel_production" in request.POST:
            self.object.cancel()
            return redirect(reverse_lazy("production:production-list"))
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
        # after receiving we no longer have a dedicated list; return to
        # the main job log so the updated status is visible.
        return reverse_lazy("production:production-list")


class ProductionDashboardView(TemplateView):
    template_name = "production/production_dashboard.html"

    def get_context_data(self, **kwargs):
        from django.db.models import Count

        context = super().get_context_data(**kwargs)
        context["total_boms"] = BillOfMaterials.objects.count()
        context["active_jobs"] = Production.objects.filter(closed=False).count()
        context["completed_jobs"] = Production.objects.filter(complete=True).count()
        # count products that have a shortage AND have a BOM (can be produced)
        # AND are not already fully covered by active production jobs
        from inventory.models import Inventory
        from django.db.models import Sum, F, OuterRef, Subquery, IntegerField
        from django.db.models.functions import Coalesce
        producible_ids = set(
            BillOfMaterials.objects.values_list("product_id", flat=True)
        )
        job_subquery = (
            Production.objects
            .filter(product_id=OuterRef("product_id"), closed=False)
            .values("product_id")
            .annotate(total=Sum(F("quantity") - F("quantity_received")))
            .values("total")
        )
        context["producible_low_stock"] = (
            Inventory.objects
            .filter(required_cached__gt=0, product_id__in=producible_ids)
            .annotate(pending_job=Coalesce(Subquery(job_subquery, output_field=IntegerField()), 0))
            .filter(pending_job__lt=F("required_cached"))
            .count()
        )
        return context
