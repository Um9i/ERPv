import csv

from django import forms
from django.contrib.auth.mixins import LoginRequiredMixin
from django.forms.models import inlineformset_factory
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from .forms import (
    CustomerContactForm,
    CustomerForm,
    CustomerProductForm,
    RequiredSOLineFormSet,
    SalesOrderForm,
    SalesOrderLineForm,
)
from .models import (
    Customer,
    CustomerContact,
    CustomerProduct,
    PickList,
    PickListLine,
    SalesLedger,
    SalesOrder,
    SalesOrderLine,
)

_CUSTOMER_PREFILL_FIELDS = [
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


class CustomerCreateView(LoginRequiredMixin, CreateView):
    model = Customer
    template_name = "sales/customer_form.html"
    form_class = CustomerForm

    def get_initial(self):
        initial = super().get_initial()
        for field in _CUSTOMER_PREFILL_FIELDS:
            if field in self.request.GET:
                initial[field] = self.request.GET[field]
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        paired_pk = self.request.session.pop("link_customer_to_paired", None)
        if paired_pk:
            from config.models import PairedInstance

            PairedInstance.objects.filter(pk=paired_pk, customer__isnull=True).update(
                customer=self.object
            )
        return response

    def get_success_url(self):
        return reverse_lazy("sales:customer-detail", args=[self.object.pk])


class CustomerUpdateView(LoginRequiredMixin, UpdateView):
    model = Customer
    template_name = "sales/customer_form.html"
    form_class = CustomerForm
    success_url = reverse_lazy("sales:customer-list")


class CustomerDeleteView(LoginRequiredMixin, DeleteView):
    model = Customer
    template_name = "sales/customer_confirm_delete.html"
    success_url = reverse_lazy("sales:customer-list")


class CustomerListView(LoginRequiredMixin, ListView):
    model = Customer
    template_name = "sales/customer_list.html"
    context_object_name = "customers"
    paginate_by = 20

    def get_queryset(self):
        qs = Customer.objects.all().order_by("name")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "")
        return context


class CustomerDetailView(LoginRequiredMixin, DetailView):
    model = Customer
    template_name = "sales/customer_detail.html"
    context_object_name = "customer"

    def get_context_data(self, **kwargs):
        from decimal import Decimal

        from django.core.paginator import Paginator
        from django.db.models import Sum

        context = super().get_context_data(**kwargs)
        customer = self.object
        order_list = customer.customer_sales_orders.all()
        prod_list = (
            customer.customer_products.select_related("product")
            .all()
            .order_by("product__name")
        )
        contacts_list = customer.customer_contacts.all().order_by("name")

        order_page = self.request.GET.get("order_page")
        prod_page = self.request.GET.get("cp_page")
        ct_page = self.request.GET.get("ct_page")

        order_paginator = Paginator(order_list, 5)
        prod_paginator = Paginator(prod_list, 5)
        ct_paginator = Paginator(contacts_list, 5)

        context["sales_orders"] = order_paginator.get_page(order_page)
        context["customer_products"] = prod_paginator.get_page(prod_page)
        context["customer_contacts"] = ct_paginator.get_page(ct_page)

        # Analytics
        context["total_orders"] = order_list.count()
        context["open_orders"] = (
            order_list.filter(sales_order_lines__complete=False).distinct().count()
        )
        context["total_revenue"] = SalesLedger.objects.filter(
            customer=customer
        ).aggregate(total=Sum("value"))["total"] or Decimal("0.00")
        context["recent_orders"] = order_list.order_by("-created_at")[:10]
        context["top_products"] = (
            SalesLedger.objects.filter(customer=customer)
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


class CustomerContactCreateView(LoginRequiredMixin, CreateView):
    model = CustomerContact
    template_name = "sales/customer_contact_form.html"
    form_class = CustomerContactForm
    success_url = reverse_lazy("sales:customer-list")

    def get_initial(self):
        initial = super().get_initial()
        customer_id = self.request.GET.get("customer")
        if customer_id:
            initial["customer"] = customer_id
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        customer_id = self.request.GET.get("customer")
        if customer_id:
            form.fields["customer"].widget = forms.HiddenInput()
        return form

    def get_success_url(self):
        return reverse_lazy("sales:customer-detail", args=[self.object.customer.pk])


class CustomerContactUpdateView(LoginRequiredMixin, UpdateView):
    model = CustomerContact
    template_name = "sales/customer_contact_form.html"
    form_class = CustomerContactForm

    def get_success_url(self):
        return reverse_lazy("sales:customer-detail", args=[self.object.customer.pk])


class CustomerContactDeleteView(LoginRequiredMixin, DeleteView):
    model = CustomerContact
    template_name = "sales/customer_contact_confirm_delete.html"

    def get_success_url(self):
        return reverse_lazy("sales:customer-detail", args=[self.object.customer.pk])


class CustomerProductCreateView(LoginRequiredMixin, CreateView):
    model = CustomerProduct
    template_name = "sales/customer_product_form.html"
    form_class = CustomerProductForm
    success_url = reverse_lazy("sales:customer-list")

    def get_initial(self):
        initial = super().get_initial()
        customer_id = self.request.GET.get("customer")
        if customer_id:
            initial["customer"] = customer_id
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        customer_id = self.request.GET.get("customer")
        if customer_id:
            form.fields["customer"].widget = forms.HiddenInput()
        return form

    def get_success_url(self):
        return reverse_lazy("sales:customer-detail", args=[self.object.customer.pk])


class CustomerProductUpdateView(LoginRequiredMixin, UpdateView):
    model = CustomerProduct
    template_name = "sales/customer_product_form.html"
    form_class = CustomerProductForm
    success_url = reverse_lazy("sales:customer-list")

    def form_valid(self, form):
        from main.audit import log_field_changes

        log_field_changes(form.instance, ["price"], user=self.request.user)
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("sales:customer-detail", args=[self.object.customer.pk])


class CustomerProductDeleteView(LoginRequiredMixin, DeleteView):
    model = CustomerProduct
    template_name = "sales/customer_product_confirm_delete.html"
    success_url = reverse_lazy("sales:customer-list")

    def get_success_url(self):
        return reverse_lazy("sales:customer-detail", args=[self.object.customer.pk])


class CustomerSalesOrderListView(LoginRequiredMixin, ListView):
    model = SalesOrder
    template_name = "sales/customer_salesorder_list.html"
    context_object_name = "sales_orders"
    paginate_by = 20

    def get_queryset(self):
        customer_id = self.kwargs.get("pk")
        return SalesOrder.objects.filter(customer_id=customer_id).select_related(
            "customer"
        )


class CustomerProductListView(LoginRequiredMixin, ListView):
    model = CustomerProduct
    template_name = "sales/customer_product_list.html"
    context_object_name = "customer_products"
    paginate_by = 20

    def get_queryset(self):
        customer_id = self.kwargs.get("pk")
        return CustomerProduct.objects.filter(customer_id=customer_id).select_related(
            "customer", "product"
        )


class CustomerProductIDsView(LoginRequiredMixin, DetailView):
    model = Customer

    def get(self, request, *args, **kwargs):
        customer = self.get_object()
        ids = list(
            CustomerProduct.objects.filter(customer=customer).values_list(
                "id", flat=True
            )
        )
        from django.http import JsonResponse

        return JsonResponse({"product_ids": ids})


class SalesOrderCreateView(LoginRequiredMixin, CreateView):
    model = SalesOrder
    template_name = "sales/sales_order_form.html"
    form_class = SalesOrderForm
    success_url = reverse_lazy("sales:customer-list")

    def get_initial(self):
        initial = super().get_initial()
        customer_id = self.request.GET.get("customer")
        if customer_id:
            initial["customer"] = customer_id
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        customer_id = self.request.GET.get("customer")
        if customer_id:
            form.fields["customer"].widget = forms.HiddenInput()
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        LineFormset = inlineformset_factory(
            SalesOrder,
            SalesOrderLine,
            form=SalesOrderLineForm,
            formset=RequiredSOLineFormSet,
            extra=1,
            can_delete=True,
            min_num=1,
            validate_min=True,
        )
        if self.request.POST:
            context["lines_formset"] = LineFormset(self.request.POST)
        else:
            context["lines_formset"] = LineFormset()

        customer_id = self.request.POST.get("customer") or self.request.GET.get(
            "customer"
        )
        if customer_id:
            try:
                customer_obj = Customer.objects.get(pk=customer_id)
                allowed = CustomerProduct.objects.filter(customer=customer_obj)
            except Customer.DoesNotExist:
                allowed = CustomerProduct.objects.none()
            for f in context["lines_formset"]:
                f.fields["product"].queryset = allowed

        # hide the DELETE checkbox — removal is handled by the JS remove button
        for f in context["lines_formset"]:
            if "DELETE" in f.fields:
                f.fields["DELETE"].widget = forms.HiddenInput()

        # let the template know whether the customer is already chosen so it
        # can show the line-items section immediately
        context["customer_known"] = bool(customer_id)
        context["has_customers"] = Customer.objects.exists()

        return context

    def form_valid(self, form):
        context = self.get_context_data(form=form)
        lines_formset = context.get("lines_formset")
        if lines_formset.is_valid():
            form.instance.created_by = self.request.user
            form.instance.updated_by = self.request.user
            self.object = form.save()
            lines_formset.instance = self.object
            lines_formset.save()
            # auto-generate a pick list for the new order
            PickList.generate_for_order(self.object)
            return super().form_valid(form)
        else:
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse_lazy("sales:customer-detail", args=[self.object.customer.pk])


class SalesOrderListView(LoginRequiredMixin, ListView):
    model = SalesOrder
    template_name = "sales/sales_order_list.html"
    context_object_name = "sales_orders"

    def get_queryset(self):
        from django.db.models import Exists, OuterRef, Q

        qs = (
            SalesOrder.objects.select_related("customer")
            .annotate(
                has_open_lines=Exists(
                    SalesOrderLine.objects.filter(
                        sales_order=OuterRef("pk"),
                        complete=False,
                    )
                ),
            )
            .order_by("-created_at")
        )
        status = self.request.GET.get("status", "open").lower()
        if status == "open":
            qs = qs.filter(has_open_lines=True)
        elif status == "closed":
            qs = qs.filter(has_open_lines=False)
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(customer__name__icontains=q) | Q(pk__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        from django.core.paginator import Paginator

        from inventory.models import Inventory

        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        page = self.request.GET.get("page")
        paginator = Paginator(qs, 15)
        page_obj = paginator.get_page(page)

        orders = list(page_obj.object_list)
        order_ids = [o.pk for o in orders]

        # Bulk-load open lines for this page to avoid N+1 queries
        # Each line: (sales_order_id, product__product_id, remaining_qty)
        open_lines = (
            SalesOrderLine.objects.filter(
                sales_order_id__in=order_ids,
                complete=False,
            )
            .select_related("product__product")
            .values_list(
                "sales_order_id",
                "product__product_id",
                "quantity",
                "quantity_shipped",
            )
        )

        # group demand by order
        from collections import defaultdict

        demand_map = defaultdict(list)  # order_id -> [(product_id, remaining)]
        product_ids = set()
        for order_id, prod_id, qty, shipped in open_lines:
            remaining = max(qty - shipped, 0)
            if remaining > 0:
                demand_map[order_id].append((prod_id, remaining))
                product_ids.add(prod_id)

        # single inventory query for all required products
        inv_map = (
            dict(
                Inventory.objects.filter(product_id__in=product_ids).values_list(
                    "product_id", "quantity"
                )
            )
            if product_ids
            else {}
        )

        for order in orders:
            lines = demand_map.get(order.pk, [])
            if not order.has_open_lines:
                # closed order — no stock check needed
                order.stock_ok = None
            elif not lines:
                order.stock_ok = True
            else:
                order.stock_ok = all(
                    inv_map.get(prod_id, 0) >= needed for prod_id, needed in lines
                )

        page_obj.object_list = orders
        context["sales_orders"] = page_obj
        context["q"] = self.request.GET.get("q", "")
        context["status"] = self.request.GET.get("status", "open").lower()
        return context


class SalesOrderDetailView(LoginRequiredMixin, DetailView):
    model = SalesOrder
    template_name = "sales/sales_order_detail.html"
    context_object_name = "sales_order"

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if "close_order" in request.POST:
            open_lines = self.object.sales_order_lines.filter(complete=False)
            for line in open_lines:
                line.complete = True
                line.closed = True
                line.save(update_fields=["complete", "closed"])
            self.object.save(update_fields=["updated_at"])
            from django.shortcuts import redirect

            return redirect(request.path)
        if "update_ship_by_date" in request.POST:
            from django.shortcuts import redirect

            if self.object.status == "Closed":
                return redirect(request.path)
            raw = request.POST.get("ship_by_date", "").strip()
            if raw:
                from datetime import date as date_cls

                self.object.ship_by_date = date_cls.fromisoformat(raw)
            else:
                self.object.ship_by_date = None
            self.object.save(update_fields=["ship_by_date", "updated_at"])
            return redirect(request.path)
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sales_order = self.object
        context["lines"] = sales_order.sales_order_lines.select_related("product").all()
        return context


class SalesOrderShipView(LoginRequiredMixin, DetailView):
    model = SalesOrder
    template_name = "sales/sales_order_ship.html"
    context_object_name = "sales_order"

    def get_context_data(self, **kwargs):
        from inventory.models import Inventory

        context = super().get_context_data(**kwargs)
        all_lines = list(
            self.object.sales_order_lines.select_related("product__product").all()
        )
        open_product_ids = {
            line.product.product_id for line in all_lines if not line.complete
        }
        inv_map = (
            dict(
                Inventory.objects.filter(product_id__in=open_product_ids).values_list(
                    "product_id", "quantity"
                )
            )
            if open_product_ids
            else {}
        )
        any_shortage = False
        for line in all_lines:
            if line.complete:
                line.stock = None
                line.stock_ok = None
                line.max_shippable = 0
            else:
                stock = inv_map.get(line.product.product_id, 0)
                line.stock = stock
                line.stock_ok = stock >= line.remaining
                line.max_shippable = min(line.remaining, max(stock, 0))
                if not line.stock_ok:
                    any_shortage = True
        context["lines"] = all_lines
        context["any_shortage"] = any_shortage
        return context

    def post(self, request, *args, **kwargs):
        # wrap whole operation in a transaction so select_for_update works
        from django.db import transaction

        self.object = self.get_object()
        ship_all = "ship_all" in request.POST
        touched = False
        errors = []

        with transaction.atomic():
            # iterate lines to attempt shipment, but validate stock first
            for line in self.object.sales_order_lines.filter(complete=False):
                if ship_all:
                    qty = line.remaining
                else:
                    key = f"shipped_{line.id}"
                    if key not in request.POST:
                        continue
                    try:
                        qty = int(request.POST[key])
                    except ValueError:
                        continue
                if qty <= 0:
                    # line may be fully shipped but not yet flagged complete
                    if line.quantity_shipped >= line.quantity:
                        line.complete = True
                        line.closed = True
                        line.save(update_fields=["complete", "closed"])
                    continue
                # before we touch inventory ensure sufficient quantity exists
                from inventory.models import Inventory, InventoryLedger
                from sales.models import SalesLedger

                try:
                    inv = Inventory.objects.select_for_update().get(
                        product=line.product.product
                    )
                except Inventory.DoesNotExist:
                    inv = None
                if inv is None or (inv.quantity - qty) < 0:
                    errors.append(
                        f"Not enough inventory to ship {qty} of {line.product.product.name}."
                    )
                    continue

                # perform updates
                touched = True
                inv.quantity -= qty
                inv.save(update_fields=["quantity", "last_updated"])

                # deduct from stock locations that hold inventory
                from inventory.models import InventoryLocation

                remaining_to_deduct = qty
                locations_used = []
                stock_locs = list(
                    InventoryLocation.objects.select_for_update()
                    .filter(inventory=inv, quantity__gt=0)
                    .order_by("location__name")
                )
                for sl in stock_locs:
                    if remaining_to_deduct <= 0:
                        break
                    deduct = min(sl.quantity, remaining_to_deduct)
                    sl.quantity -= deduct
                    sl.save(update_fields=["quantity", "last_updated"])
                    remaining_to_deduct -= deduct
                    locations_used.append(sl.location)

                InventoryLedger.objects.create(
                    product=line.product.product,
                    quantity=-abs(qty),
                    action="Sales Order",
                    transaction_id=self.object.pk,
                    location=locations_used[0] if len(locations_used) == 1 else None,
                )
                SalesLedger.objects.create(
                    product=line.product.product,
                    quantity=qty,
                    customer=self.object.customer,
                    value=(line.product.price or 0) * qty,
                    transaction_id=self.object.pk,
                )

                line.quantity_shipped = line.quantity_shipped + qty
                if line.quantity_shipped >= line.quantity:
                    line.complete = True
                    line.closed = True
                    try:
                        line.value = line.product.price * line.quantity
                    except Exception:
                        line.value = None
                fields = ["quantity_shipped"]
                if line.complete:
                    fields += ["complete", "closed", "value"]
                line.save(update_fields=fields)
        if errors:
            # re-render form with error messages
            context = self.get_context_data()
            context["errors"] = errors
            from django.shortcuts import render

            return render(request, self.template_name, context)
        if touched:
            self.object.save(update_fields=["updated_at"])
        return redirect(self.get_success_url())

    def get_success_url(self):
        # after shipping redirect back to the main list (shipping list removed)
        return reverse_lazy("sales:sales-order-list")


class SalesDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "sales/sales_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.utils import timezone

        today = timezone.localdate()
        context["total_orders"] = SalesOrder.objects.count()
        # orders with ship_by_date today or earlier
        due_qs = SalesOrder.objects.filter(ship_by_date__lte=today)
        # how many of today's due SOs have had any shipment
        context["shipped_orders"] = (
            due_qs.filter(sales_order_lines__quantity_shipped__gt=0).distinct().count()
        )
        # SOs due today or earlier with any open lines
        pending_qs = (
            due_qs.filter(sales_order_lines__complete=False)
            .distinct()
            .select_related("customer")
        )
        context["pending_shipping"] = pending_qs.count()
        context["pending_orders_list"] = pending_qs[:10]
        context["total_customers"] = Customer.objects.count()
        due_total = context["shipped_orders"] + context["pending_shipping"]
        context["fulfillment_rate"] = (
            round(context["shipped_orders"] / due_total * 100) if due_total else 0
        )
        context["fulfilled_orders"] = context["shipped_orders"]
        return context


class SalesOrderInvoiceView(LoginRequiredMixin, DetailView):
    model = SalesOrder

    def get(self, request, *args, **kwargs):
        from django.http import HttpResponse
        from django.template.loader import render_to_string
        from weasyprint import HTML

        order = self.get_object()
        context = {
            "order": order,
            "lines": order.sales_order_lines.select_related("product__product").all(),
        }
        html_string = render_to_string("sales/invoice.html", context, request)
        html = HTML(
            string=html_string,
            base_url=request.build_absolute_uri("/"),
        )
        pdf_bytes = html.write_pdf()
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'inline; filename="invoice-{order.order_number}.pdf"'
        )
        return response


class PickListCreateView(DetailView):
    """Generate a new pick list for a sales order."""

    model = SalesOrder

    def post(self, request, *args, **kwargs):
        order = self.get_object()
        pick_list = PickList.generate_for_order(order)
        return redirect("sales:pick-list-detail", pk=pick_list.pk)

    def get(self, request, *args, **kwargs):
        # GET also generates for convenience
        order = self.get_object()
        pick_list = PickList.generate_for_order(order)
        return redirect("sales:pick-list-detail", pk=pick_list.pk)


class PickListDetailView(DetailView):
    model = PickList
    template_name = "sales/pick_list_detail.html"
    context_object_name = "pick_list"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lines"] = self.object.lines.select_related(
            "sales_order_line__product__product",
            "location",
        ).all()
        return context


class PickConfirmView(LoginRequiredMixin, DetailView):
    """Scan-to-pick confirmation workflow for warehouse staff."""

    model = PickList
    template_name = "sales/pick_confirm.html"
    context_object_name = "pick_list"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lines = list(
            self.object.lines.select_related(
                "sales_order_line__product__product",
                "location",
            ).all()
        )
        context["lines"] = lines
        total = sum(1 for ln in lines if not ln.is_shortage)
        confirmed = sum(1 for ln in lines if ln.confirmed and not ln.is_shortage)
        context["total_lines"] = total
        context["confirmed_lines"] = confirmed
        context["all_confirmed"] = self.object.all_confirmed
        return context

    def post(self, request, *args, **kwargs):
        from django.http import JsonResponse
        from django.utils import timezone

        from inventory.models import Product

        self.object = self.get_object()
        scan_value = request.POST.get("scan_value", "").strip()
        line_id = request.POST.get("line_id", "").strip()

        # Manual confirm by line ID
        if line_id:
            try:
                line = self.object.lines.get(pk=int(line_id), is_shortage=False)
            except PickListLine.DoesNotExist, ValueError:
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse({"ok": False, "error": "Line not found."})
                return redirect(request.path)
            line.confirmed = True
            line.confirmed_at = timezone.now()
            line.save(update_fields=["confirmed", "confirmed_at"])
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse(
                    {
                        "ok": True,
                        "line_id": line.pk,
                        "all_confirmed": self.object.all_confirmed,
                    }
                )
            return redirect(request.path)

        # Barcode / QR scan
        if scan_value:
            product = (
                Product.objects.filter(barcode=scan_value).first()
                or Product.objects.filter(sku=scan_value).first()
            )
            if not product:
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse(
                        {"ok": False, "error": f"No product matches scan: {scan_value}"}
                    )
                return redirect(request.path)

            # Find the first unconfirmed line for this product on this pick list
            line = (
                self.object.lines.filter(
                    sales_order_line__product__product=product,
                    is_shortage=False,
                    confirmed=False,
                )
                .select_related("sales_order_line__product__product")
                .first()
            )
            if not line:
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse(
                        {
                            "ok": False,
                            "error": f"{product.name} has no unconfirmed lines on this pick list.",
                        }
                    )
                return redirect(request.path)

            line.confirmed = True
            line.confirmed_at = timezone.now()
            line.save(update_fields=["confirmed", "confirmed_at"])
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse(
                    {
                        "ok": True,
                        "line_id": line.pk,
                        "product_name": product.name,
                        "all_confirmed": self.object.all_confirmed,
                    }
                )
            return redirect(request.path)

        return redirect(request.path)


class PickConfirmResetView(LoginRequiredMixin, View):
    """Reset all confirmations on a pick list."""

    def post(self, request, pk):
        pick_list = PickList.objects.get(pk=pk)
        pick_list.lines.update(confirmed=False, confirmed_at=None)
        return redirect("sales:pick-confirm", pk=pick_list.pk)


class ProductQRCodeView(LoginRequiredMixin, View):
    """Generate a QR code PNG for a product's barcode or SKU."""

    def get(self, request, pk):
        import io

        import qrcode

        from inventory.models import Product

        product = Product.objects.get(pk=pk)
        value = product.barcode or product.sku or product.name
        img = qrcode.make(value, box_size=8, border=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return HttpResponse(buf.getvalue(), content_type="image/png")


class SalesOrderExportView(LoginRequiredMixin, View):
    """Export sales orders as CSV."""

    def get(self, request):
        from django.db.models import Exists, OuterRef, Q

        qs = (
            SalesOrder.objects.select_related("customer")
            .annotate(
                has_open_lines=Exists(
                    SalesOrderLine.objects.filter(
                        sales_order=OuterRef("pk"),
                        complete=False,
                    )
                ),
            )
            .order_by("-created_at")
        )

        status_value = request.GET.get("status", "").strip().lower()
        if status_value == "open":
            qs = qs.filter(has_open_lines=True)
        elif status_value == "closed":
            qs = qs.filter(has_open_lines=False)

        q = request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(customer__name__icontains=q) | Q(pk__icontains=q))

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="sales_orders.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "Order Number",
                "Customer",
                "Status",
                "Ship By",
                "Created At",
                "Total Amount",
            ]
        )
        for order in qs:
            writer.writerow(
                [
                    order.order_number,
                    order.customer.name,
                    "Open" if order.has_open_lines else "Closed",
                    order.ship_by_date or "",
                    order.created_at.strftime("%Y-%m-%d %H:%M"),
                    order.total_amount,
                ]
            )
        return response
