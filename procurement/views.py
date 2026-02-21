from .models import (
    Supplier,
    SupplierContact,
    SupplierProduct,
    PurchaseOrder,
    PurchaseOrderLine,
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
from django.forms.models import inlineformset_factory
from django.db.models import F


class SupplierCreateView(CreateView):
    model = Supplier
    template_name = "procurement/supplier_form.html"
    fields = ["name", "address", "phone", "email", "website"]
    success_url = reverse_lazy("procurement:supplier-list")


class SupplierUpdateView(UpdateView):
    model = Supplier
    template_name = "procurement/supplier_form.html"
    fields = ["name", "address", "phone", "email", "website"]
    success_url = reverse_lazy("procurement:supplier-list")


class SupplierDeleteView(DeleteView):
    model = Supplier
    template_name = "procurement/supplier_confirm_delete.html"
    success_url = reverse_lazy("procurement:supplier-list")


class SupplierListView(ListView):
    model = Supplier
    template_name = "procurement/supplier_list.html"
    context_object_name = "suppliers"

    def get_queryset(self):
        """Allow filtering by a simple ``q`` query parameter.

        We only expose a basic case-insensitive name search right now; the
        calling templates render a search box and include any existing query
        when paginating.
        """
        qs = Supplier.objects.all().order_by("name")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        from django.core.paginator import Paginator

        context = super().get_context_data(**kwargs)
        # rely on ``get_queryset`` so the pagination respects the search
        supplier_list = self.get_queryset()
        page_num = self.request.GET.get("page")
        paginator = Paginator(supplier_list, 20)
        context["suppliers"] = paginator.get_page(page_num)
        # preserve the search term for templates
        context["q"] = self.request.GET.get("q", "")
        return context


class SupplierDetailView(DetailView):
    model = Supplier
    template_name = "procurement/supplier_detail.html"
    context_object_name = "supplier"

    def get_context_data(self, **kwargs):
        # include related objects so the template can render tables without
        # additional queries in the template itself; add pagination
        from django.core.paginator import Paginator

        context = super().get_context_data(**kwargs)
        supplier = self.object
        po_list = supplier.supplier_purchase_orders.all()
        # enforce ordering to avoid paginator warnings
        pp_list = supplier.supplier_products.all().order_by('product__name')

        po_page_number = self.request.GET.get("po_page")
        pp_page_number = self.request.GET.get("sp_page")

        po_paginator = Paginator(po_list, 5)
        pp_paginator = Paginator(pp_list, 5)

        context["purchase_orders"] = po_paginator.get_page(po_page_number)
        context["supplier_products"] = pp_paginator.get_page(pp_page_number)
        return context


class SupplierContactCreateView(CreateView):
    model = SupplierContact
    template_name = "procurement/supplier_contact_form.html"
    fields = ["supplier", "name", "email", "phone"]
    success_url = reverse_lazy("procurement:supplier-list")


class SupplierProductCreateView(CreateView):
    model = SupplierProduct
    template_name = "procurement/supplier_product_form.html"
    fields = ["supplier", "product", "cost"]
    success_url = reverse_lazy("procurement:supplier-list")

    def get_initial(self):
        initial = super().get_initial()
        supplier_id = self.request.GET.get("supplier")
        if supplier_id:
            initial["supplier"] = supplier_id
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        supplier_id = self.request.GET.get("supplier")
        if supplier_id:
            form.fields["supplier"].widget = forms.HiddenInput()
        return form

    def get_success_url(self):
        # after creating a supplier product return to that supplier's detail
        return reverse_lazy("procurement:supplier-detail", args=[self.object.supplier.pk])


class SupplierProductUpdateView(UpdateView):
    model = SupplierProduct
    template_name = "procurement/supplier_product_form.html"
    fields = ["supplier", "product", "cost"]
    success_url = reverse_lazy("procurement:supplier-list")

    def get_success_url(self):
        # after updating a supplier product return to that supplier's detail
        return reverse_lazy("procurement:supplier-detail", args=[self.object.supplier.pk])


class SupplierProductDeleteView(DeleteView):
    model = SupplierProduct
    template_name = "procurement/supplier_product_confirm_delete.html"
    success_url = reverse_lazy("procurement:supplier-list")

    def get_success_url(self):
        # after deleting a supplier product return to that supplier's detail
        return reverse_lazy("procurement:supplier-detail", args=[self.object.supplier.pk])


class SupplierPurchaseOrderListView(ListView):
    model = PurchaseOrder
    template_name = "procurement/supplier_purchaseorder_list.html"
    context_object_name = "purchase_orders"

    def get_queryset(self):
        supplier_id = self.kwargs.get("pk")
        return PurchaseOrder.objects.filter(supplier_id=supplier_id)


class SupplierProductListView(ListView):
    model = SupplierProduct
    template_name = "procurement/supplier_product_list.html"
    context_object_name = "supplier_products"

    def get_queryset(self):
        supplier_id = self.kwargs.get("pk")
        return SupplierProduct.objects.filter(supplier_id=supplier_id)


class SupplierProductIDsView(DetailView):
    """Return JSON list of *supplier‑product* IDs for a supplier.

    This matches the values used in the purchase order line form, which
    reference the SupplierProduct primary key rather than the underlying
    Product. The javascript code relies on these IDs when showing/hiding
    options.
    """
    model = Supplier

    def get(self, request, *args, **kwargs):
        supplier = self.get_object()
        ids = list(
            SupplierProduct.objects.filter(supplier=supplier)
            .values_list("id", flat=True)
        )
        from django.http import JsonResponse

        return JsonResponse({"product_ids": ids})


class PurchaseOrderCreateView(CreateView):
    model = PurchaseOrder
    template_name = "procurement/purchase_order_form.html"
    fields = ["supplier"]
    success_url = reverse_lazy("procurement:supplier-list")


class ProcurementDashboardView(TemplateView):
    template_name = "procurement/procurement_dashboard.html"

    def get_context_data(self, **kwargs):
        from django.db.models import Count

        context = super().get_context_data(**kwargs)
        context["total_purchase_orders"] = PurchaseOrder.objects.count()
        context["pending_receiving"] = PurchaseOrderLine.objects.filter(complete=False).count()
        context["total_suppliers"] = Supplier.objects.count()
        return context


class PurchaseOrderCreateView(CreateView):
    model = PurchaseOrder
    template_name = "procurement/purchase_order_form.html"
    fields = ["supplier"]
    success_url = reverse_lazy("procurement:supplier-list")

    def get_initial(self):
        initial = super().get_initial()
        supplier_id = self.request.GET.get("supplier")
        if supplier_id:
            initial["supplier"] = supplier_id
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        supplier_id = self.request.GET.get("supplier")
        if supplier_id:
            form.fields["supplier"].widget = forms.HiddenInput()
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # create an inline formset for the purchase order lines
        # don't offer complete or deletion on the initial create formset;
        # completion is handled later via the line save logic and deletion not
        # necessary at create time.
        LineFormset = inlineformset_factory(
            PurchaseOrder,
            PurchaseOrderLine,
            fields=["product", "quantity"],
            extra=1,
            can_delete=False,
        )
        if self.request.POST:
            context["lines_formset"] = LineFormset(self.request.POST)
        else:
            context["lines_formset"] = LineFormset()

        # if we know the supplier either from GET or submitted POST data,
        # limit the product dropdowns on each line to that supplier's products.
        supplier_id = self.request.POST.get("supplier") or self.request.GET.get(
            "supplier"
        )
        if supplier_id:
            try:
                supplier_obj = Supplier.objects.get(pk=supplier_id)
                allowed = SupplierProduct.objects.filter(supplier=supplier_obj)
            except Supplier.DoesNotExist:
                allowed = SupplierProduct.objects.none()
            for f in context["lines_formset"]:
                f.fields["product"].queryset = allowed

        return context

    def form_valid(self, form):
        context = self.get_context_data(form=form)
        lines_formset = context.get("lines_formset")
        if lines_formset.is_valid():
            # save the purchase order first so we can attach lines to it
            self.object = form.save()
            lines_formset.instance = self.object
            lines_formset.save()
            return super().form_valid(form)
        else:
            return self.form_invalid(form)

    def get_success_url(self):
        # once saved redirect to the supplier's detail view so the user can
        # immediately see the new order in context
        return reverse_lazy(
            "procurement:supplier-detail", args=[self.object.supplier.pk]
        )


class PurchaseOrderListView(ListView):
    model = PurchaseOrder
    template_name = "procurement/purchase_order_list.html"
    context_object_name = "purchase_orders"

    def get_queryset(self):
        qs = PurchaseOrder.objects.all().order_by("-created_at")
        q = self.request.GET.get("q", "").strip()
        if q:
            # allow searching by supplier name or order primary key
            from django.db.models import Q

            qs = qs.filter(Q(supplier__name__icontains=q) | Q(pk__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        # mirror supplier list pagination behaviour
        from django.core.paginator import Paginator

        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        page = self.request.GET.get("page")
        paginator = Paginator(qs, 15)
        context["purchase_orders"] = paginator.get_page(page)
        context["q"] = self.request.GET.get("q", "")
        return context


class PurchaseOrderDetailView(DetailView):
    model = PurchaseOrder
    template_name = "procurement/purchase_order_detail.html"
    context_object_name = "purchase_order"

    def post(self, request, *args, **kwargs):
        # support a manual "close order" action from the detail page.
        self.object = self.get_object()
        if "close_order" in request.POST:
            # mark every non‑complete line as complete/closed and ensure
            # quantity_received and value reflect the full ordered amount.
            # we use queryset.update() so that the save() hooks (which would
            # adjust inventory) are bypassed; closing an order should not
            # change stock levels.
            from django.db.models import F

            open_lines = self.object.purchase_order_lines.filter(complete=False)
            # iterate so we can safely compute values and set closed/complete
            # without triggering the inventory adjustment logic in save().
            for line in open_lines:
                # mark lines closed without touching receive counts or price
                line.complete = True
                line.closed = True
                # do not modify quantity_received or value; the order is being
                # closed administratively rather than as a receipt.
                line.save(update_fields=["complete", "closed"])
            # update order timestamp to signal change
            self.object.save(update_fields=["updated_at"])
            # simply reload the detail page
            from django.shortcuts import redirect
            return redirect(request.path)
        # delegate other POSTs if we ever need them (none today)
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        purchase_order = self.object
        context["lines"] = purchase_order.purchase_order_lines.select_related(
            "product"
        ).all()
        # allow template to decide whether to render close button
        context["can_close"] = purchase_order.status == "Open"
        return context


class PurchaseOrderReceivingListView(ListView):
    model = PurchaseOrder
    template_name = "procurement/purchase_order_receiving_list.html"
    context_object_name = "purchase_orders"

    def get_queryset(self):
        # show only purchase orders that have unreceived lines
        qs = PurchaseOrder.objects.filter(
            purchase_order_lines__complete=False
        ).distinct().order_by("-created_at")
        q = self.request.GET.get("q", "").strip()
        if q:
            from django.db.models import Q

            qs = qs.filter(Q(supplier__name__icontains=q) | Q(pk__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        from django.core.paginator import Paginator
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        page = self.request.GET.get("page")
        paginator = Paginator(qs, 10)
        context["purchase_orders"] = paginator.get_page(page)
        context["q"] = self.request.GET.get("q", "")
        return context


class PurchaseOrderReceiveView(DetailView):
    model = PurchaseOrder
    template_name = "procurement/purchase_order_receive.html"
    context_object_name = "purchase_order"

    def post(self, request, *args, **kwargs):
        # process received quantities and mark lines complete
        self.object = self.get_object()
        # if receive-all button was clicked, treat each line as if the
        # remaining amount were entered
        receive_all = "receive_all" in request.POST
        touched = False
        for line in self.object.purchase_order_lines.filter(complete=False):
            if receive_all:
                qty = line.remaining
            else:
                key = f"received_{line.id}"
                if key not in request.POST:
                    continue
                try:
                    qty = int(request.POST[key])
                except ValueError:
                    continue
            # any positive quantity should be treated as received;
            if qty > 0:
                touched = True
                # update inventory and ledgers manually (qty may be less
                # than order quantity, so we don't rely on the model hook)
                from inventory.models import Inventory, InventoryLedger
                from procurement.models import PurchaseLedger

                from django.utils import timezone
                Inventory.objects.filter(
                    product=line.product.product
                ).update(quantity=F("quantity") + qty, last_updated=timezone.now())
                InventoryLedger.objects.create(
                    product=line.product.product,
                    quantity=qty,
                    action="Purchase Order",
                    transaction_id=self.object.pk,
                )
                PurchaseLedger.objects.create(
                    product=line.product.product,
                    quantity=qty,
                    supplier=self.object.supplier,
                    value=(line.product.cost or 0) * qty,
                    transaction_id=self.object.pk,
                )

                # update received quantity; only mark complete/closed when
                # we've now received at least the ordered amount
                line.quantity_received = line.quantity_received + qty
                if line.quantity_received >= line.quantity:
                    line.complete = True
                    line.closed = True
                    # store the full-order value once the line is closed; do
                    # not touch it during partial receipts.
                    try:
                        line.value = line.product.cost * line.quantity
                    except Exception:
                        line.value = None
                # the monetary *order* value should stay the same; we only want
                # to record it once the line is fully received.  partial
                # receipts leave `value` untouched.
                fields = ["quantity_received"]
                if line.complete:
                    fields += ["complete", "closed", "value"]
                line.save(update_fields=fields)
        # if any lines were changed, update the purchase order timestamp so
        # users can see that something happened
        if touched:
            # auto_now takes care of the actual value
            self.object.save(update_fields=["updated_at"])
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy("procurement:purchase-order-receiving-list")
