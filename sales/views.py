from .models import (
    Customer,
    CustomerContact,
    CustomerProduct,
    SalesOrder,
    SalesOrderLine,
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


class CustomerCreateView(CreateView):
    model = Customer
    template_name = "sales/customer_form.html"
    fields = ["name", "address", "phone", "email", "website"]
    success_url = reverse_lazy("sales:customer-list")


class CustomerUpdateView(UpdateView):
    model = Customer
    template_name = "sales/customer_form.html"
    fields = ["name", "address", "phone", "email", "website"]
    success_url = reverse_lazy("sales:customer-list")


class CustomerDeleteView(DeleteView):
    model = Customer
    template_name = "sales/customer_confirm_delete.html"
    success_url = reverse_lazy("sales:customer-list")


class CustomerListView(ListView):
    model = Customer
    template_name = "sales/customer_list.html"
    context_object_name = "customers"

    def get_queryset(self):
        qs = Customer.objects.all().order_by("name")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        from django.core.paginator import Paginator

        context = super().get_context_data(**kwargs)
        customer_list = self.get_queryset()
        page_num = self.request.GET.get("page")
        paginator = Paginator(customer_list, 20)
        context["customers"] = paginator.get_page(page_num)
        context["q"] = self.request.GET.get("q", "")
        return context


class CustomerDetailView(DetailView):
    model = Customer
    template_name = "sales/customer_detail.html"
    context_object_name = "customer"

    def get_context_data(self, **kwargs):
        from django.core.paginator import Paginator

        context = super().get_context_data(**kwargs)
        customer = self.object
        order_list = customer.customer_sales_orders.all()
        prod_list = customer.customer_products.all().order_by('product__name')

        order_page = self.request.GET.get("order_page")
        prod_page = self.request.GET.get("cp_page")

        order_paginator = Paginator(order_list, 5)
        prod_paginator = Paginator(prod_list, 5)

        context["sales_orders"] = order_paginator.get_page(order_page)
        context["customer_products"] = prod_paginator.get_page(prod_page)
        return context


class CustomerContactCreateView(CreateView):
    model = CustomerContact
    template_name = "sales/customer_contact_form.html"
    fields = ["customer", "name", "email", "phone"]
    success_url = reverse_lazy("sales:customer-list")


class CustomerProductCreateView(CreateView):
    model = CustomerProduct
    template_name = "sales/customer_product_form.html"
    fields = ["customer", "product", "price"]
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


class CustomerProductUpdateView(UpdateView):
    model = CustomerProduct
    template_name = "sales/customer_product_form.html"
    fields = ["customer", "product", "price"]
    success_url = reverse_lazy("sales:customer-list")

    def get_success_url(self):
        return reverse_lazy("sales:customer-detail", args=[self.object.customer.pk])


class CustomerProductDeleteView(DeleteView):
    model = CustomerProduct
    template_name = "sales/customer_product_confirm_delete.html"
    success_url = reverse_lazy("sales:customer-list")

    def get_success_url(self):
        return reverse_lazy("sales:customer-detail", args=[self.object.customer.pk])


class CustomerSalesOrderListView(ListView):
    model = SalesOrder
    template_name = "sales/customer_salesorder_list.html"
    context_object_name = "sales_orders"

    def get_queryset(self):
        customer_id = self.kwargs.get("pk")
        return SalesOrder.objects.filter(customer_id=customer_id)


class CustomerProductListView(ListView):
    model = CustomerProduct
    template_name = "sales/customer_product_list.html"
    context_object_name = "customer_products"

    def get_queryset(self):
        customer_id = self.kwargs.get("pk")
        return CustomerProduct.objects.filter(customer_id=customer_id)


class CustomerProductIDsView(DetailView):
    model = Customer

    def get(self, request, *args, **kwargs):
        customer = self.get_object()
        ids = list(
            CustomerProduct.objects.filter(customer=customer)
            .values_list("id", flat=True)
        )
        from django.http import JsonResponse

        return JsonResponse({"product_ids": ids})


class SalesOrderCreateView(CreateView):
    model = SalesOrder
    template_name = "sales/sales_order_form.html"
    fields = ["customer"]
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
            fields=["product", "quantity"],
            extra=1,
            can_delete=False,
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

    def get_success_url(self):
        return reverse_lazy("sales:customer-detail", args=[self.object.customer.pk])


class SalesOrderListView(ListView):
    model = SalesOrder
    template_name = "sales/sales_order_list.html"
    context_object_name = "sales_orders"

    def get_queryset(self):
        qs = SalesOrder.objects.all().order_by("-created_at")
        q = self.request.GET.get("q", "").strip()
        if q:
            from django.db.models import Q

            qs = qs.filter(Q(customer__name__icontains=q) | Q(pk__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        from django.core.paginator import Paginator

        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        page = self.request.GET.get("page")
        paginator = Paginator(qs, 15)
        context["sales_orders"] = paginator.get_page(page)
        context["q"] = self.request.GET.get("q", "")
        return context


class SalesOrderDetailView(DetailView):
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
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sales_order = self.object
        context["lines"] = sales_order.sales_order_lines.select_related(
            "product"
        ).all()
        context["can_close"] = sales_order.status == "Open"
        return context


class SalesOrderShipListView(ListView):
    model = SalesOrder
    template_name = "sales/sales_order_ship_list.html"
    context_object_name = "sales_orders"

    def get_queryset(self):
        qs = SalesOrder.objects.filter(
            sales_order_lines__complete=False
        ).distinct().order_by("-created_at")
        q = self.request.GET.get("q", "").strip()
        if q:
            from django.db.models import Q

            qs = qs.filter(Q(customer__name__icontains=q) | Q(pk__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        from django.core.paginator import Paginator

        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        page = self.request.GET.get("page")
        paginator = Paginator(qs, 10)
        context["sales_orders"] = paginator.get_page(page)
        context["q"] = self.request.GET.get("q", "")
        return context


class SalesOrderShipView(DetailView):
    model = SalesOrder
    template_name = "sales/sales_order_ship.html"
    context_object_name = "sales_order"

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        ship_all = "ship_all" in request.POST
        touched = False
        errors = []
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
                continue
            # before we touch inventory ensure sufficient quantity exists
            from inventory.models import Inventory, InventoryLedger
            from sales.models import SalesLedger

            try:
                inv = Inventory.objects.select_for_update().get(product=line.product.product)
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
            InventoryLedger.objects.create(
                product=line.product.product,
                quantity=-abs(qty),
                action="Sales Order",
                transaction_id=self.object.pk,
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
        return reverse_lazy("sales:sales-order-ship-list")


class SalesDashboardView(TemplateView):
    template_name = "sales/sales_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_orders"] = SalesOrder.objects.count()
        context["shipped_orders"] = SalesOrderLine.objects.filter(quantity_shipped__gt=0).count()
        # count of lines still awaiting shipment (not marked complete)
        context["pending_shipping"] = SalesOrderLine.objects.filter(complete=False).count()
        context["total_customers"] = Customer.objects.count()
        return context
