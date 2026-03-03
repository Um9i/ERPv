from django.shortcuts import render
from .models import Product, Inventory, InventoryAdjust
from .forms import ProductForm, InventoryAdjustForm
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
    TemplateView,
)
from django.urls import reverse_lazy
from django.http import JsonResponse


class ProductCreateView(CreateView):
    model = Product
    template_name = "inventory/product_form.html"
    form_class = ProductForm
    success_url = reverse_lazy("inventory:inventory-list")

    def get_success_url(self):
        return reverse_lazy("inventory:inventory-detail", args=[self.object.pk])


class ProductUpdateView(UpdateView):
    model = Product
    template_name = "inventory/product_form.html"
    form_class = ProductForm
    success_url = reverse_lazy("inventory:inventory-list")


class ProductDeleteView(DeleteView):
    model = Product
    template_name = "inventory/product_confirm_delete.html"
    success_url = reverse_lazy("inventory:inventory-list")


class InventoryListView(ListView):
    model = Inventory
    template_name = "inventory/inventory_list.html"
    context_object_name = "inventories"

    def get_queryset(self):
        qs = Inventory.objects.all().select_related("product")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(product__name__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        from django.core.paginator import Paginator

        context = super().get_context_data(**kwargs)
        inv_list = self.get_queryset()
        page = self.request.GET.get("page")
        paginator = Paginator(inv_list, 20)
        context["inventories"] = paginator.get_page(page)
        context["q"] = self.request.GET.get("q", "")
        return context


class InventoryDetailView(DetailView):
    model = Inventory
    template_name = "inventory/inventory_detail.html"
    context_object_name = "inventory"

    def get_queryset(self):
        return Inventory.objects.all().select_related("product")

    def get_context_data(self, **kwargs):
        from django.core.paginator import Paginator
        from django.db.models import Sum, F
        # import lazily to avoid circular deps
        from sales.models import SalesOrderLine
        from procurement.models import PurchaseOrderLine
        from production.models import Production

        context = super().get_context_data(**kwargs)
        inv = self.object
        # ledger pagination
        ledger_list = inv.product.inventory_ledger.all().order_by("-date")
        page = self.request.GET.get("page")
        paginator = Paginator(ledger_list, 10)
        ledger_page = paginator.get_page(page)

        # ── Compute running balance anchored to current stock ──
        # Walk all entries newest-first to assign a balance to every entry,
        # then attach balances to the paginated subset.
        all_entries_desc = list(inv.product.inventory_ledger.all().order_by("-date").values_list("pk", "quantity"))
        # build balance map: start from current qty, walk backwards (newest first)
        balance_map = {}
        running = inv.quantity
        for pk, qty in all_entries_desc:
            balance_map[pk] = running
            running -= qty
        # `running` now equals the implied opening balance before all ledger entries

        # annotate paginated entries with their balance
        for entry in ledger_page:
            entry.balance = balance_map.get(entry.pk, None)

        context["ledger"] = ledger_page

        # ── Build chart history anchored to real stock ──
        # Walk entries oldest-first; start from the implied opening balance
        all_entries_asc = list(
            inv.product.inventory_ledger.all()
            .order_by("date")
            .values_list("quantity", "date")
        )
        opening_balance = running  # leftover from the desc walk above
        history = []
        dates = []
        total = opening_balance
        for qty, dt in all_entries_asc:
            total += qty
            dates.append(dt.strftime("%Y-%m-%d %H:%M"))
            history.append(total)

        context["history_dates"] = dates
        context["history_qty"] = history

        # monthly activity summaries for charts
        from django.db.models.functions import TruncMonth
        # sales by month
        sales_months = (
            SalesOrderLine.objects.filter(product__product=inv.product)
            .annotate(month=TruncMonth('sales_order__created_at'))
            .values('month')
            .annotate(total=Sum('quantity'))
            .order_by('month')
        )
        # purchases by month
        purchase_months = (
            PurchaseOrderLine.objects.filter(product__product=inv.product)
            .annotate(month=TruncMonth('purchase_order__created_at'))
            .values('month')
            .annotate(total=Sum('quantity'))
            .order_by('month')
        )
        # production by month
        production_months = (
            Production.objects.filter(product=inv.product)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(total=Sum('quantity'))
            .order_by('month')
        )
        # convert to parallel lists (months as YYYY-MM format)
        m_dates = []
        m_sales = []
        m_purch = []
        m_prod = []
        # build mapping for each type for easier access
        sales_map = {entry['month']: entry['total'] or 0 for entry in sales_months}
        purch_map = {entry['month']: entry['total'] or 0 for entry in purchase_months}
        prod_map = {entry['month']: entry['total'] or 0 for entry in production_months}
        # unify all month keys
        all_months = sorted(set(list(sales_map.keys()) + list(purch_map.keys()) + list(prod_map.keys())))
        for m in all_months:
            m_dates.append(m.strftime("%Y-%m"))
            m_sales.append(sales_map.get(m, 0))
            m_purch.append(purch_map.get(m, 0))
            m_prod.append(prod_map.get(m, 0))
        context['monthly_dates'] = m_dates
        context['monthly_sales'] = m_sales
        context['monthly_purchases'] = m_purch
        context['monthly_production'] = m_prod
        # compute pending amounts for this product
        # sales pending: sum of quantities not yet shipped
        sales_qs = SalesOrderLine.objects.filter(
            product__product=inv.product,
            complete=False,
        )
        context["sales_pending"] = sales_qs.aggregate(total=Sum(F("quantity") - F("quantity_shipped"))) ["total"] or 0
        # purchase pending: sum of remaining quantity to receive
        po_qs = PurchaseOrderLine.objects.filter(
            product__product=inv.product,
            complete=False,
        )
        context["purchase_pending"] = po_qs.aggregate(total=Sum(F("quantity") - F("quantity_received")))["total"] or 0
        # production pending: sum of remaining production quantity
        prod_qs = Production.objects.filter(
            product=inv.product,
            closed=False,
        ).filter(quantity__gt=F('quantity_received'))
        context["production_pending"] = prod_qs.aggregate(total=Sum(F("quantity") - F("quantity_received")))["total"] or 0

        # shortage: how much demand exceeds all available + incoming supply
        available = inv.quantity + context["purchase_pending"] + context["production_pending"]
        context["required_qty"] = max(0, context["sales_pending"] - available)

        # bundle all chart data for json_script (consumed by static JS)
        context["chart_data"] = {
            "sales_pending": context["sales_pending"],
            "purchase_pending": context["purchase_pending"],
            "production_pending": context["production_pending"],
            "required_qty": context["required_qty"],
            "history_dates": context["history_dates"],
            "history_qty": context["history_qty"],
            "monthly_dates": context["monthly_dates"],
            "monthly_sales": context["monthly_sales"],
            "monthly_purchases": context["monthly_purchases"],
            "monthly_production": context["monthly_production"],
        }
        return context


class InventoryAdjustCreateView(CreateView):
    model = InventoryAdjust
    template_name = "inventory/inventory_adjust_form.html"
    form_class = InventoryAdjustForm
    success_url = reverse_lazy("inventory:inventory-list")

    def get_initial(self):
        initial = super().get_initial()
        inventory = Inventory.objects.select_related("product").get(pk=self.kwargs.get("pk"))
        initial["product"] = inventory.product
        return initial

    def get_form(self, *args, **kwargs):
        form = super().get_form(*args, **kwargs)
        form.fields["product"].disabled = True
        if "complete" in form.fields:
            del form.fields["complete"]
        return form

    def form_valid(self, form):
        inventory = Inventory.objects.select_related("product").get(pk=self.kwargs.get("pk"))
        form.instance.product = inventory.product
        form.instance.complete = True
        return super().form_valid(form)


class InventoryDashboardView(TemplateView):
    """Dashboard showing inventory metrics for the inventory app."""

    template_name = "inventory/inventory_dashboard.html"

    def get_context_data(self, **kwargs):
        # mirror previous dashboard calculations formerly misplaced on LowStockListView
        from django.db.models import Sum

        context = super().get_context_data(**kwargs)
        context["total_products"] = Product.objects.count()
        context["total_inventory_items"] = Inventory.objects.count()
        context["total_quantity"] = (
            Inventory.objects.aggregate(total=Sum("quantity"))["total"] or 0
        )
        # compute monetary stock value using per-unit costs
        stock_val = 0
        for inv in Inventory.objects.select_related("product").all():
            stock_val += inv.quantity * inv.product.unit_cost
        context["stock_value"] = stock_val
        # optionally show list of products with required shortage
        req = getattr(self, "request", None)
        if req and req.GET.get("required"):
            req_items = []
            for inv in Inventory.objects.select_related("product").all():
                if inv.required > 0:
                    req_items.append({
                        "product": inv.product,
                        "required": inv.required,
                    })
            context["required_items"] = req_items
        return context


class LowStockListView(TemplateView):
    """Page listing all products currently below required stock."""

    template_name = "inventory/low_stock_list.html"

    def get_context_data(self, **kwargs):
        from django.core.paginator import Paginator
        from django.urls import reverse

        from procurement.services import best_supplier_products, pending_po_by_product
        from production.services import bom_product_ids, pending_jobs_by_product

        context = super().get_context_data(**kwargs)

        # gather low-stock inventories; use cached shortage for the broad query
        inv_list = list(
            Inventory.objects
            .select_related("product")
            .filter(required_cached__gt=0)
        )
        product_ids = [inv.product_id for inv in inv_list]

        po_map = pending_po_by_product(product_ids)
        job_map = pending_jobs_by_product(product_ids)
        bom_ids = bom_product_ids(product_ids)
        supplier_map = best_supplier_products(product_ids)

        items = []
        supplier_items: dict[int, list[tuple[int, int]]] = {}

        for inv in inv_list:
            # compute live required to ensure current stock is reflected
            required_qty = inv.required
            if required_qty <= 0:
                continue
            prod_amount = job_map.get(inv.product_id, 0)
            po_amount = po_map.get(inv.product_id, 0)
            needed_po = max(required_qty - po_amount, 0)

            supplierproduct = supplier_map.get(inv.product_id)
            supplier_id = supplierproduct.supplier_id if supplierproduct else None
            supplierproduct_id = supplierproduct.pk if supplierproduct else None
            if supplier_id and needed_po > 0:
                supplier_items.setdefault(supplier_id, []).append(
                    (supplierproduct_id, needed_po)
                )

            has_bom = inv.product_id in bom_ids
            can_start = has_bom and prod_amount < required_qty

            can_order = supplier_id is not None and needed_po > 0
            order_qty = max(required_qty - prod_amount, 0)

            items.append({
                "product": inv.product,
                "required": required_qty,
                "quantity": inv.quantity,
                "production_amount": prod_amount,
                "po_amount": po_amount,
                "has_bom": has_bom,
                "can_start_job": can_start,
                "supplier_id": supplier_id,
                "supplierproduct_id": supplierproduct_id,
                "can_order": can_order,
                "order_qty": order_qty,
                "po_order_qty": needed_po,
            })

        # apply filter: 'purchasable' = has a supplier and not fully covered by open POs
        # 'producible' = has a BOM and not fully covered by active production jobs
        filter_by = self.request.GET.get("filter", "")
        if filter_by == "purchasable":
            items = [e for e in items if e["supplier_id"] is not None and e["po_amount"] < e["required"]]
        elif filter_by == "producible":
            items = [e for e in items if e["has_bom"] and e["production_amount"] < e["required"]]
        context["filter_by"] = filter_by

        # sort items by requirement descending so highest shortages appear first
        items.sort(key=lambda ent: ent["required"], reverse=True)
        # generate purchase-order URLs for each entry that has a supplier
        for entry in items:
            sid = entry.get("supplier_id")
            if sid is not None and entry.get("can_order", False):
                pairs = supplier_items.get(sid, [])
                qs = "&".join(f"item={pid}:{qty}" for pid, qty in pairs)
                entry["po_url"] = f"{reverse('procurement:purchase-order-create')}?supplier={sid}&{qs}"
            else:
                entry["po_url"] = None

        # paginate the results
        page = self.request.GET.get("page")
        paginator = Paginator(items, 20)
        context["required_items"] = paginator.get_page(page)
        return context

    def form_valid(self, form):
        inventory = Inventory.objects.select_related("product").get(pk=self.kwargs.get("pk"))
        form.instance.product = inventory.product
        form.instance.complete = True
        return super().form_valid(form)


class InventoryListApiView(TemplateView):
    """API view to return inventory data for dashboard charts."""

    def get(self, request, *args, **kwargs):
        from django.db.models import Sum

        # compute inventory levels for all products
        data = []
        for inv in Inventory.objects.select_related("product").all():
            data.append({
                "product": inv.product.name,
                "quantity": inv.quantity,
                "required": inv.required,
            })
        return JsonResponse(data, safe=False)
