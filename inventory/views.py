from django.shortcuts import render
from .models import Product, Inventory, InventoryAdjust
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
    fields = ["name"]
    success_url = reverse_lazy("inventory:inventory-list")


class ProductUpdateView(UpdateView):
    model = Product
    template_name = "inventory/product_form.html"
    fields = ["name"]
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
        context["ledger"] = paginator.get_page(page)
        # build time series of inventory levels from ledger
        history = []
        total = 0
        dates = []
        for entry in inv.product.inventory_ledger.all().order_by("date"):
            total += entry.quantity
            dates.append(entry.date.strftime("%Y-%m-%d %H:%M"))
            history.append(total)
        context["history_dates"] = dates
        context["history_qty"] = history
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
        # shortage required field
        context["required_qty"] = inv.required
        return context


class InventoryAdjustCreateView(CreateView):
    model = InventoryAdjust
    template_name = "inventory/inventory_adjust_form.html"
    fields = ["product", "quantity"]
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
        # collect all inventories where a shortage is present
        from procurement.models import PurchaseOrderLine
        from production.models import Production

        context = super().get_context_data(**kwargs)
        items = []
        from django.db.models import Sum, F

        from production.models import BillOfMaterials

        # mapping suppliers to the items we could order from them
        supplier_items: dict[int, list[tuple[int, int]]] = {}

        # compute a tie-breaker ranking: total cost of all products a supplier offers
        from procurement.models import SupplierProduct
        total_cost_by_supplier = (
            SupplierProduct.objects
            .values('supplier')
            .annotate(total=Sum('cost'))
            .order_by('supplier')
        )
        supplier_total = {entry['supplier']: entry['total'] for entry in total_cost_by_supplier}

        # retrieve all inventories once and build helper maps to avoid N+1
        inv_list = list(
            Inventory.objects.select_related("product")
            .prefetch_related("product__production_allocated")
            .all()
        )
        prod_ids = [inv.product_id for inv in inv_list]

        # supplier-products grouped by product id, sorted by cost
        sp_qs = SupplierProduct.objects.filter(product_id__in=prod_ids).order_by("product_id","cost")
        sp_map: dict[int, list[SupplierProduct]] = {}
        for sp in sp_qs:
            sp_map.setdefault(sp.product_id, []).append(sp)

        # which products have BOMs
        bom_ids = set(
            BillOfMaterials.objects.filter(product_id__in=prod_ids)
            .values_list('product_id', flat=True)
        )

        # aggregate pending PO and production quantities per product
        po_vals = (
            PurchaseOrderLine.objects.filter(product__product_id__in=prod_ids, complete=False)
            .annotate(rem=F('quantity') - F('quantity_received'))
            .values('product__product_id')
            .annotate(total=Sum('rem'))
        )
        po_map = {v['product__product_id']: v['total'] or 0 for v in po_vals}

        job_vals = (
            Production.objects.filter(product_id__in=prod_ids, closed=False)
            .annotate(rem=F('quantity') - F('quantity_received'))
            .values('product_id')
            .annotate(total=Sum('rem'))
        )
        job_map = {v['product']: v['total'] or 0 for v in job_vals}

        # now build items list using the precomputed maps
        for inv in inv_list:
            if inv.required <= 0:
                continue

            prod_amount = job_map.get(inv.product_id, 0)
            po_amount = po_map.get(inv.product_id, 0)
            needed_po = max(inv.required - po_amount, 0)

            has_bom = inv.product_id in bom_ids
            can_start = has_bom and prod_amount < inv.required

            supplier_id = None
            supplierproduct_id = None
            candidates = sp_map.get(inv.product_id, [])
            if candidates:
                lowest_cost = candidates[0].cost
                ties = [sp for sp in candidates if sp.cost == lowest_cost]
                if len(ties) > 1:
                    ties.sort(key=lambda sp: supplier_total.get(sp.supplier_id, 0))
                sp = ties[0]
                supplier_id = sp.supplier_id
                supplierproduct_id = sp.pk
                supplier_items.setdefault(supplier_id, []).append(
                    (supplierproduct_id, needed_po)
                )

            can_order = supplier_id is not None and needed_po > 0
            order_qty = max(inv.required - prod_amount, 0)

            items.append({
                "product": inv.product,
                "required": inv.required,
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
        # generate purchase-order URLs for each entry that has a supplier
        from django.urls import reverse
        for entry in items:
            sid = entry.get("supplier_id")
            if sid is not None and entry.get("can_order", False):
                pairs = supplier_items.get(sid, [])
                qs = "&".join(f"item={pid}:{qty}" for pid, qty in pairs)
                entry["po_url"] = f"{reverse('procurement:purchase-order-create')}?supplier={sid}&{qs}"
            else:
                entry["po_url"] = None
        context["required_items"] = items
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
