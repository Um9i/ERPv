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
    ProductionReceiveForm,
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
            context["lines_formset"] = LineFormset(
                self.request.POST, instance=self.object
            )
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
        from .services import build_bom_tree

        context = super().get_context_data(**kwargs)
        bom = self.object
        items = bom.bom_items.select_related("product").all()
        page = self.request.GET.get("page")
        paginator = Paginator(items, 10)
        context["bom_items"] = paginator.get_page(page)
        context["bom_tree"] = build_bom_tree(bom.product)
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
        if self.object and self.object.product_id not in qs.values_list(
            "id", flat=True
        ):
            qs = qs | Product.objects.filter(pk=self.object.product_id)
        form.fields["product"].queryset = qs
        return form


class ProductionListView(ListView):
    model = Production
    template_name = "production/production_list.html"
    context_object_name = "productions"

    def get_queryset(self):
        qs = (
            Production.objects.all()
            .order_by(
                "closed",
                F("due_date").asc(nulls_last=True),
                "-pk",
            )
            .select_related("product")
        )
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
        from collections import defaultdict
        from datetime import timedelta
        from django.core.paginator import Paginator
        from django.utils import timezone
        from inventory.models import Inventory

        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        page = self.request.GET.get("page")
        paginator = Paginator(qs, 15)
        page_obj = paginator.get_page(page)

        # Evaluate the page into a list so we can enrich each object
        productions = list(page_obj.object_list)

        # Bulk-compute materials_available to avoid N+1 queries
        product_ids = [p.product_id for p in productions]

        # Load BOM items for all products on this page
        bom_rows = BOMItem.objects.filter(bom__product_id__in=product_ids).values_list(
            "bom__product_id", "product_id", "quantity"
        )
        bom_map = defaultdict(list)
        component_ids = set()
        for prod_id, comp_id, qty in bom_rows:
            bom_map[prod_id].append((comp_id, qty))
            component_ids.add(comp_id)

        # Load inventory for all required components in one query
        inv_map = (
            dict(
                Inventory.objects.filter(product_id__in=component_ids).values_list(
                    "product_id", "quantity"
                )
            )
            if component_ids
            else {}
        )

        for job in productions:
            components = bom_map.get(job.product_id, [])
            if not components:
                job.materials_ok = False
            else:
                job.materials_ok = all(
                    inv_map.get(comp_id, 0) >= comp_qty * job.quantity
                    for comp_id, comp_qty in components
                )

        # Replace the page's object_list so the template uses enriched objects
        page_obj.object_list = productions
        context["productions"] = page_obj
        context["q"] = self.request.GET.get("q", "")
        context["status"] = self.request.GET.get("status", "").lower()
        context["today"] = timezone.now().date()
        context["today_plus_7"] = timezone.now().date() + timedelta(days=7)
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
        from django.contrib import messages
        from .services import receive_production_into_location

        self.object = self.get_object()
        if "cancel_production" in request.POST:
            self.object.cancel()
            return redirect(reverse_lazy("production:production-list"))
        if "complete_production" in request.POST:
            self.object.complete = True
            self.object.save()
            return redirect(request.path)
        if "receive_production" in request.POST:
            form = ProductionReceiveForm(request.POST, instance=self.object)
            if form.is_valid():
                location = form.cleaned_data.get("location")
                quantity = form.cleaned_data["quantity_to_receive"]
                try:
                    if location:
                        receive_production_into_location(
                            self.object.pk, quantity, location.pk
                        )
                    else:
                        self.object.quantity_received += quantity
                        self.object.save()
                except Exception as e:
                    messages.error(request, str(e))
                return redirect(request.path)
            else:
                context = self.get_context_data(receive_form=form)
                return self.render_to_response(context)
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        from datetime import timedelta
        from django.utils import timezone
        from inventory.models import Inventory

        context = super().get_context_data(**kwargs)
        job = self.object
        context["bom"] = job.bom()
        context["today"] = timezone.now().date()
        context["today_plus_7"] = timezone.now().date() + timedelta(days=7)

        components = []
        if job.bom():
            for item in job.bom():
                try:
                    inv = Inventory.objects.get(product=item.product)
                    stock = inv.quantity
                except Inventory.DoesNotExist:
                    stock = 0
                required = item.quantity * job.quantity
                required_remaining = item.quantity * job.remaining
                shortfall = max(required_remaining - stock, 0)
                components.append(
                    {
                        "product": item.product,
                        "per_unit": item.quantity,
                        "required": required,
                        "required_remaining": required_remaining,
                        "stock": stock,
                        "shortfall": shortfall,
                        "ok": shortfall == 0,
                    }
                )
        context["components"] = components
        context["any_shortage"] = any(not c["ok"] for c in components)

        from .services import build_bom_tree

        context["bom_tree"] = build_bom_tree(job.product, quantity=job.remaining)

        unit_cost = job.product.unit_cost
        sale_price = job.product.effective_sale_price

        total_cost = unit_cost * job.quantity
        produced_cost = unit_cost * job.quantity_received
        produced_value = sale_price * job.quantity_received

        if produced_value and produced_value > 0:
            margin_pct = ((produced_value - produced_cost) / produced_value) * 100
        else:
            margin_pct = None

        if sale_price and sale_price > 0:
            projected_value = sale_price * job.quantity
            projected_margin_pct = (
                (projected_value - total_cost) / projected_value
            ) * 100
        else:
            projected_value = None
            projected_margin_pct = None

        context.update(
            {
                "unit_cost": unit_cost,
                "sale_price": sale_price,
                "total_cost": total_cost,
                "produced_cost": produced_cost,
                "produced_value": produced_value,
                "margin_pct": margin_pct,
                "projected_value": projected_value,
                "projected_margin_pct": projected_margin_pct,
            }
        )
        if "receive_form" not in kwargs:
            context["receive_form"] = ProductionReceiveForm(instance=job)
        else:
            context["receive_form"] = kwargs["receive_form"]
        return context


class ProductionReceiveView(DetailView):
    model = Production
    template_name = "production/production_receive.html"
    context_object_name = "production"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "form" not in kwargs:
            context["form"] = ProductionReceiveForm(instance=self.object)
        return context

    def post(self, request, *args, **kwargs):
        from django.contrib import messages
        from .services import receive_production_into_location

        self.object = self.get_object()
        form = ProductionReceiveForm(request.POST, instance=self.object)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        location = form.cleaned_data.get("location")
        quantity = form.cleaned_data["quantity_to_receive"]

        try:
            if location:
                receive_production_into_location(self.object.pk, quantity, location.pk)
            else:
                self.object.quantity_received += quantity
                self.object.save()
        except Exception as e:
            messages.error(request, str(e))
            return redirect(request.path)

        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy("production:production-detail", args=[self.object.pk])


class ProductionDashboardView(TemplateView):
    template_name = "production/production_dashboard.html"

    def get_context_data(self, **kwargs):
        from django.db.models import Count

        context = super().get_context_data(**kwargs)
        context["total_boms"] = BillOfMaterials.objects.count()
        context["total_jobs"] = Production.objects.count()
        context["active_jobs"] = Production.objects.filter(closed=False).count()
        context["completed_jobs"] = Production.objects.filter(complete=True).count()
        context["completion_rate"] = (
            round(context["completed_jobs"] / context["total_jobs"] * 100)
            if context["total_jobs"]
            else 0
        )
        # count products that have a shortage AND have a BOM (can be produced)
        # AND are not already fully covered by active production jobs
        from inventory.models import Inventory
        from django.db.models import Sum, F, OuterRef, Subquery, IntegerField
        from django.db.models.functions import Coalesce

        producible_ids = set(
            BillOfMaterials.objects.values_list("product_id", flat=True)
        )
        job_subquery = (
            Production.objects.filter(product_id=OuterRef("product_id"), closed=False)
            .values("product_id")
            .annotate(total=Sum(F("quantity") - F("quantity_received")))
            .values("total")
        )
        context["producible_low_stock"] = (
            Inventory.objects.filter(
                required_cached__gt=0, product_id__in=producible_ids
            )
            .annotate(
                pending_job=Coalesce(
                    Subquery(job_subquery, output_field=IntegerField()), 0
                )
            )
            .filter(pending_job__lt=F("required_cached"))
            .count()
        )
        return context
