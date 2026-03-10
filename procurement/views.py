import hmac

from django import forms
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import F
from django.forms.models import inlineformset_factory
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from .forms import (
    PurchaseOrderForm,
    PurchaseOrderLineForm,
    SupplierContactForm,
    SupplierForm,
    SupplierProductForm,
)
from .models import (
    PurchaseLedger,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierContact,
    SupplierProduct,
)

_SUPPLIER_PREFILL_FIELDS = [
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


class SupplierCreateView(LoginRequiredMixin, CreateView):
    model = Supplier
    template_name = "procurement/supplier_form.html"
    form_class = SupplierForm

    def get_initial(self):
        initial = super().get_initial()
        for field in _SUPPLIER_PREFILL_FIELDS:
            if field in self.request.GET:
                initial[field] = self.request.GET[field]
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        paired_pk = self.request.session.pop("link_supplier_to_paired", None)
        if paired_pk:
            from config.models import PairedInstance
            from config.notifications import _notify_remote_customer

            PairedInstance.objects.filter(pk=paired_pk, supplier__isnull=True).update(
                supplier=self.object
            )
            paired_instance = PairedInstance.objects.filter(pk=paired_pk).first()
            if paired_instance and not _notify_remote_customer(paired_instance):
                from django.contrib import messages

                messages.warning(
                    self.request,
                    f"Could not notify {paired_instance.name} of customer link — check connectivity.",
                )
        return response

    def get_success_url(self):
        # after creating a supplier return to that supplier's detail
        return reverse_lazy("procurement:supplier-detail", args=[self.object.pk])


class SupplierUpdateView(LoginRequiredMixin, UpdateView):
    model = Supplier
    template_name = "procurement/supplier_form.html"
    form_class = SupplierForm
    success_url = reverse_lazy("procurement:supplier-list")


class SupplierDeleteView(LoginRequiredMixin, DeleteView):
    model = Supplier
    template_name = "procurement/supplier_confirm_delete.html"
    success_url = reverse_lazy("procurement:supplier-list")


class SupplierListView(LoginRequiredMixin, ListView):
    model = Supplier
    template_name = "procurement/supplier_list.html"
    context_object_name = "suppliers"
    paginate_by = 20

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
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "")
        return context


class SupplierDetailView(LoginRequiredMixin, DetailView):
    model = Supplier
    template_name = "procurement/supplier_detail.html"
    context_object_name = "supplier"

    def get_context_data(self, **kwargs):
        # include related objects so the template can render tables without
        # additional queries in the template itself; add pagination
        from decimal import Decimal

        from django.core.paginator import Paginator
        from django.db.models import Sum

        context = super().get_context_data(**kwargs)
        supplier = self.object
        po_list = supplier.supplier_purchase_orders.all()
        # enforce ordering to avoid paginator warnings
        pp_list = supplier.supplier_products.all().order_by("product__name")
        # contacts
        contacts_list = supplier.supplier_contacts.all().order_by("name")

        po_page_number = self.request.GET.get("po_page")
        pp_page_number = self.request.GET.get("sp_page")
        ct_page_number = self.request.GET.get("ct_page")

        po_paginator = Paginator(po_list, 5)
        pp_paginator = Paginator(pp_list, 5)
        ct_paginator = Paginator(contacts_list, 5)

        context["purchase_orders"] = po_paginator.get_page(po_page_number)
        context["supplier_products"] = pp_paginator.get_page(pp_page_number)
        context["supplier_contacts"] = ct_paginator.get_page(ct_page_number)

        # Analytics
        context["total_orders"] = po_list.count()
        context["open_orders"] = (
            po_list.filter(purchase_order_lines__complete=False).distinct().count()
        )
        context["total_spend"] = PurchaseLedger.objects.filter(
            supplier=supplier
        ).aggregate(total=Sum("value"))["total"] or Decimal("0.00")
        context["recent_orders"] = po_list.order_by("-created_at")[:10]
        context["top_products"] = (
            PurchaseLedger.objects.filter(supplier=supplier)
            .values(
                "product__pk",
                "product__name",
                "product__product_inventory",
            )
            .annotate(
                total_qty=Sum("quantity"),
                total_value=Sum("value"),
            )
            .order_by("-total_value")[:5]
        )
        return context


class SupplierContactCreateView(LoginRequiredMixin, CreateView):
    model = SupplierContact
    template_name = "procurement/supplier_contact_form.html"
    form_class = SupplierContactForm
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
        return reverse_lazy(
            "procurement:supplier-detail", args=[self.object.supplier.pk]
        )


class SupplierContactUpdateView(LoginRequiredMixin, UpdateView):
    model = SupplierContact
    template_name = "procurement/supplier_contact_form.html"
    form_class = SupplierContactForm

    def get_success_url(self):
        return reverse_lazy(
            "procurement:supplier-detail", args=[self.object.supplier.pk]
        )


class SupplierContactDeleteView(LoginRequiredMixin, DeleteView):
    model = SupplierContact
    template_name = "procurement/supplier_contact_confirm_delete.html"

    def get_success_url(self):
        return reverse_lazy(
            "procurement:supplier-detail", args=[self.object.supplier.pk]
        )


class SupplierProductCreateView(LoginRequiredMixin, CreateView):
    model = SupplierProduct
    template_name = "procurement/supplier_product_form.html"
    form_class = SupplierProductForm
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
        return reverse_lazy(
            "procurement:supplier-detail", args=[self.object.supplier.pk]
        )


class SupplierProductUpdateView(LoginRequiredMixin, UpdateView):
    model = SupplierProduct
    template_name = "procurement/supplier_product_form.html"
    form_class = SupplierProductForm
    success_url = reverse_lazy("procurement:supplier-list")

    def get_success_url(self):
        # after updating a supplier product return to that supplier's detail
        return reverse_lazy(
            "procurement:supplier-detail", args=[self.object.supplier.pk]
        )


class SupplierProductDeleteView(LoginRequiredMixin, DeleteView):
    model = SupplierProduct
    template_name = "procurement/supplier_product_confirm_delete.html"
    success_url = reverse_lazy("procurement:supplier-list")

    def get_success_url(self):
        # after deleting a supplier product return to that supplier's detail
        return reverse_lazy(
            "procurement:supplier-detail", args=[self.object.supplier.pk]
        )


class SupplierPurchaseOrderListView(LoginRequiredMixin, ListView):
    model = PurchaseOrder
    template_name = "procurement/supplier_purchaseorder_list.html"
    context_object_name = "purchase_orders"
    paginate_by = 20

    def get_queryset(self):
        supplier_id = self.kwargs.get("pk")
        return PurchaseOrder.objects.filter(supplier_id=supplier_id)


class SupplierProductListView(LoginRequiredMixin, ListView):
    model = SupplierProduct
    template_name = "procurement/supplier_product_list.html"
    context_object_name = "supplier_products"
    paginate_by = 20

    def get_queryset(self):
        supplier_id = self.kwargs.get("pk")
        return SupplierProduct.objects.filter(supplier_id=supplier_id)


class SupplierProductIDsView(LoginRequiredMixin, DetailView):
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
            SupplierProduct.objects.filter(supplier=supplier).values_list(
                "id", flat=True
            )
        )

        return JsonResponse({"product_ids": ids})


class PurchaseOrderDeleteView(LoginRequiredMixin, DeleteView):
    model = PurchaseOrder
    template_name = "procurement/purchase_order_confirm_delete.html"
    success_url = reverse_lazy("procurement:supplier-list")


class ProcurementDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "procurement/procurement_dashboard.html"

    def get_context_data(self, **kwargs):
        from django.db.models import Count, Q

        context = super().get_context_data(**kwargs)
        from django.utils import timezone

        today = timezone.localdate()
        context["total_purchase_orders"] = PurchaseOrder.objects.count()
        # orders due today or earlier
        due_qs = PurchaseOrder.objects.filter(due_date__lte=today)
        # how many of today's due POs are fully received (all lines complete)
        context["orders_received"] = (
            due_qs.annotate(
                total_lines=Count("purchase_order_lines"),
                complete_lines=Count(
                    "purchase_order_lines",
                    filter=Q(purchase_order_lines__complete=True),
                ),
            )
            .filter(total_lines__gt=0, total_lines=F("complete_lines"))
            .count()
        )
        # POs due today or earlier that still have open lines
        context["pending_receiving"] = (
            due_qs.filter(purchase_order_lines__complete=False).distinct().count()
        )
        context["total_suppliers"] = Supplier.objects.count()
        # count products that have a live shortage, have a supplier, and are not
        # fully covered by open purchase orders.  Use live ``required`` to avoid
        # stale cache discrepancies with the low-stock list.
        from django.urls import reverse

        from inventory.models import Inventory
        from procurement.models import SupplierProduct
        from procurement.services import best_supplier_products, pending_po_by_product

        inv_list = list(
            Inventory.objects.select_related("product").filter(required_cached__gt=0)
        )
        product_ids = [inv.product_id for inv in inv_list]
        po_map = pending_po_by_product(product_ids)
        purchasable_ids = set(
            SupplierProduct.objects.filter(product_id__in=product_ids).values_list(
                "product_id", flat=True
            )
        )
        best_sp_map = best_supplier_products(product_ids)

        purchasable_items = []
        supplier_items: dict = {}
        for inv in inv_list:
            if inv.product_id not in purchasable_ids:
                continue
            required_qty = inv.required_cached
            if required_qty <= 0:
                continue
            po_amount = po_map.get(inv.product_id, 0)
            if po_amount >= required_qty:
                continue
            shortfall = required_qty - po_amount
            sp = best_sp_map.get(inv.product_id)
            supplier_id = sp.supplier_id if sp else None
            supplierproduct_id = sp.pk if sp else None
            if supplier_id:
                supplier_items.setdefault(supplier_id, []).append(
                    (supplierproduct_id, shortfall)
                )
            purchasable_items.append(
                {
                    "product": inv.product,
                    "quantity": inv.quantity,
                    "required_cached": required_qty,
                    "po_amount": po_amount,
                    "shortfall": shortfall,
                    "supplier_id": supplier_id,
                }
            )

        for entry in purchasable_items:
            sid = entry["supplier_id"]
            if sid:
                pairs = supplier_items.get(sid, [])
                qs = "&".join(f"item={pid}:{qty}" for pid, qty in pairs)
                entry["po_url"] = (
                    f"{reverse('procurement:purchase-order-create')}?supplier={sid}&{qs}"
                )
            else:
                entry["po_url"] = None

        purchasable_items.sort(key=lambda e: e["required_cached"], reverse=True)
        context["purchasable_items"] = purchasable_items
        context["purchasable_low_stock"] = len(purchasable_items)
        due_total = context["orders_received"] + context["pending_receiving"]
        context["receipt_rate"] = (
            round(context["orders_received"] / due_total * 100) if due_total else 0
        )
        context["orders_no_lines"] = max(
            0,
            context["total_purchase_orders"]
            - context["orders_received"]
            - context["pending_receiving"],
        )
        return context


class PurchaseOrderCreateView(LoginRequiredMixin, CreateView):
    model = PurchaseOrder
    template_name = "procurement/purchase_order_form.html"
    form_class = PurchaseOrderForm
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
        # helper for creating formset class with configurable extra rows
        def make_lineformset(extra=1):
            return inlineformset_factory(
                PurchaseOrder,
                PurchaseOrderLine,
                form=PurchaseOrderLineForm,
                extra=extra,
                can_delete=True,
            )

        # handle inline formset initialisation
        if self.request.POST:
            LineFormset = make_lineformset()
            context["lines_formset"] = LineFormset(self.request.POST)
        else:
            # attempt to prepopulate from GET parameters
            initial = []
            for item in self.request.GET.getlist("item"):
                try:
                    spid, qty = item.split(":")
                    initial.append({"product": spid, "quantity": qty})
                except ValueError:
                    continue
            if initial:
                LineFormset = make_lineformset(extra=len(initial))
                context["lines_formset"] = LineFormset(initial=initial)
            else:
                LineFormset = make_lineformset()
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

        # hide the DELETE checkbox — removal is handled by the JS remove button
        for f in context["lines_formset"]:
            if "DELETE" in f.fields:
                f.fields["DELETE"].widget = forms.HiddenInput()

        # let the template know whether the supplier is already chosen so it
        # can show the line-items section immediately
        context["supplier_known"] = bool(supplier_id)
        context["has_suppliers"] = Supplier.objects.exists()
        if supplier_id:
            try:
                context["supplier_name"] = Supplier.objects.get(pk=supplier_id).name
            except Supplier.DoesNotExist:
                context["supplier_name"] = ""

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


class PurchaseOrderListView(LoginRequiredMixin, ListView):
    model = PurchaseOrder
    template_name = "procurement/purchase_order_list.html"
    context_object_name = "purchase_orders"

    def get_queryset(self):
        from django.db.models import Exists, OuterRef, Q

        qs = (
            PurchaseOrder.objects.select_related("supplier")
            .annotate(
                has_open_lines=Exists(
                    PurchaseOrderLine.objects.filter(
                        purchase_order=OuterRef("pk"),
                        complete=False,
                    )
                ),
            )
            .order_by("-created_at")
        )

        filter_value = self.request.GET.get("filter", "").strip()
        status_value = self.request.GET.get("status", "open").strip().lower()

        if status_value == "open":
            qs = qs.filter(has_open_lines=True)
        elif status_value == "closed":
            qs = qs.filter(has_open_lines=False)

        if filter_value == "received":
            qs = qs.filter(has_open_lines=False)
        elif filter_value == "pending_receiving":
            qs = qs.filter(has_open_lines=True)

        q = self.request.GET.get("q", "").strip()
        if q:
            # allow searching by supplier name or order primary key
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
        context["status"] = self.request.GET.get("status", "open").strip().lower()
        return context


class PurchaseOrderDetailView(LoginRequiredMixin, DetailView):
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
        if "update_due_date" in request.POST:
            from django.shortcuts import redirect

            if self.object.status == "Closed":
                return redirect(request.path)
            raw = request.POST.get("due_date", "").strip()
            if raw:
                from datetime import date as date_cls

                self.object.due_date = date_cls.fromisoformat(raw)
            else:
                self.object.due_date = None
            self.object.save(update_fields=["due_date", "updated_at"])
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


# PurchaseOrderReceivingListView removed – functionality overlaps
# with PurchaseOrderListView which already provides access to open orders.
# The dedicated template and URL have been deleted as well.


class PurchaseOrderReceiveView(LoginRequiredMixin, DetailView):
    model = PurchaseOrder
    template_name = "procurement/purchase_order_receive.html"
    context_object_name = "purchase_order"

    def post(self, request, *args, **kwargs):
        from inventory.services import refresh_required_cache_for_products
        from procurement.services import receive_purchase_order_line

        self.object = self.get_object()
        receive_all = "receive_all" in request.POST
        affected_product_ids: set[int] = set()
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
            product_id = receive_purchase_order_line(line, qty)
            if product_id is not None:
                affected_product_ids.add(product_id)

        if affected_product_ids:
            self.object.save(update_fields=["updated_at"])
            refresh_required_cache_for_products(affected_product_ids)
        return redirect(self.get_success_url())

    def get_success_url(self):
        # after receiving, go back to the full PO list (no standalone
        # receiving page exists any longer)
        return reverse_lazy("procurement:purchase-order-list")


@method_decorator(csrf_exempt, name="dispatch")
class NotifySupplierProductView(View):
    """Inbound: remote tells us to update the cost of a SupplierProduct."""

    def post(self, request, *args, **kwargs):
        import json
        from decimal import Decimal, InvalidOperation

        from config.models import PairedInstance

        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer "):
            return JsonResponse({"error": "Unauthorized"}, status=401)
        key = auth[len("Bearer ") :]
        paired_instance = next(
            (
                pi
                for pi in PairedInstance.objects.all()
                if hmac.compare_digest(key, pi.our_key)
            ),
            None,
        )
        if paired_instance is None:
            return JsonResponse({"error": "Unauthorized"}, status=401)

        if not paired_instance.supplier:
            return JsonResponse(
                {"error": "Supplier not linked to this paired instance"}, status=400
            )

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError, ValueError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        product_name = (data.get("product_name") or "").strip()
        cost_raw = str(data.get("cost", "")).strip()

        if not product_name:
            return JsonResponse({"error": "product_name is required"}, status=400)

        try:
            cost = Decimal(cost_raw)
        except InvalidOperation:
            return JsonResponse({"error": f"Invalid cost: {cost_raw!r}"}, status=400)

        sp = SupplierProduct.objects.filter(
            supplier=paired_instance.supplier,
            product__name__iexact=product_name,
        ).first()
        if not sp:
            return JsonResponse({"error": "SupplierProduct not found"}, status=400)

        sp.cost = cost
        sp.save(update_fields=["cost"])
        return JsonResponse({"status": "ok"})
