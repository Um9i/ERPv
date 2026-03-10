from django.shortcuts import render
from .models import (
    Product,
    Inventory,
    InventoryAdjust,
    InventoryLedger,
    Location,
    InventoryLocation,
    StockTransfer,
)
from .forms import (
    ProductForm,
    InventoryAdjustForm,
    LocationForm,
    InventoryLocationForm,
    StockTransferForm,
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
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
import hmac
from django.contrib import messages

from config.models import PairedInstance
from config.notifications import (
    _notify_remote_customer_product,
    _notify_remote_supplier_product_cost,
)


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

    def form_valid(self, form):
        old_price = (
            Product.objects.filter(pk=self.object.pk)
            .values_list("sale_price", flat=True)
            .first()
        )

        response = super().form_valid(form)
        product = self.object

        if (
            product.catalogue_item
            and product.sale_price is not None
            and product.sale_price != old_price
        ):
            paired_instances = PairedInstance.objects.filter(
                supplier__supplier_products__product=product,
                api_key__gt="",
            ).distinct()

            failed = []
            for pi in paired_instances:
                ok1 = _notify_remote_customer_product(
                    pi, product.name, product.sale_price
                )
                ok2 = _notify_remote_supplier_product_cost(
                    pi, product.name, product.sale_price
                )
                if not ok1 or not ok2:
                    failed.append(pi.name)

            if failed:
                messages.warning(
                    self.request,
                    f"Price updated locally, but failed to notify: {', '.join(failed)}.",
                )
            elif paired_instances.exists():
                messages.success(
                    self.request,
                    "Price updated and paired instances notified.",
                )

        return response

    def get_success_url(self):
        return reverse_lazy("inventory:inventory-detail", args=[self.object.pk])


class ProductDeleteView(DeleteView):
    model = Product
    template_name = "inventory/product_confirm_delete.html"
    success_url = reverse_lazy("inventory:inventory-list")


class InventoryListView(ListView):
    model = Inventory
    template_name = "inventory/inventory_list.html"
    context_object_name = "inventories"

    def get_queryset(self):
        qs = (
            Inventory.objects.all()
            .select_related("product")
            .prefetch_related("stock_locations__location")
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(product__name__icontains=q)
        catalogue = self.request.GET.get("catalogue", "").strip()
        if catalogue == "1":
            qs = qs.filter(product__catalogue_item=True)
        elif catalogue == "0":
            qs = qs.filter(product__catalogue_item=False)
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
        all_entries_desc = list(
            inv.product.inventory_ledger.all()
            .order_by("-date")
            .values_list("pk", "quantity")
        )
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
        raw_dates = []
        total = opening_balance
        for qty, dt in all_entries_asc:
            total += qty
            raw_dates.append(dt)
            history.append(total)

        if raw_dates:
            all_same_day = len(set(d.date() for d in raw_dates)) == 1
            date_fmt = "%H:%M" if all_same_day else "%d %b"
            dates = [d.strftime(date_fmt) for d in raw_dates]
        else:
            dates = []

        context["history_dates"] = dates
        context["history_qty"] = history

        # monthly activity summaries for charts
        from django.db.models.functions import TruncMonth

        # sales by month
        sales_months = (
            SalesOrderLine.objects.filter(product__product=inv.product)
            .annotate(month=TruncMonth("sales_order__created_at"))
            .values("month")
            .annotate(total=Sum("quantity"))
            .order_by("month")
        )
        # purchases by month
        purchase_months = (
            PurchaseOrderLine.objects.filter(product__product=inv.product)
            .annotate(month=TruncMonth("purchase_order__created_at"))
            .values("month")
            .annotate(total=Sum("quantity"))
            .order_by("month")
        )
        # production by month
        production_months = (
            Production.objects.filter(product=inv.product)
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(total=Sum("quantity"))
            .order_by("month")
        )
        # convert to parallel lists (months as YYYY-MM format)
        m_dates = []
        m_sales = []
        m_purch = []
        m_prod = []
        # build mapping for each type for easier access
        sales_map = {entry["month"]: entry["total"] or 0 for entry in sales_months}
        purch_map = {entry["month"]: entry["total"] or 0 for entry in purchase_months}
        prod_map = {entry["month"]: entry["total"] or 0 for entry in production_months}
        # unify all month keys
        all_months = sorted(
            set(list(sales_map.keys()) + list(purch_map.keys()) + list(prod_map.keys()))
        )
        for m in all_months:
            m_dates.append(m.strftime("%Y-%m"))
            m_sales.append(sales_map.get(m, 0))
            m_purch.append(purch_map.get(m, 0))
            m_prod.append(prod_map.get(m, 0))
        context["monthly_dates"] = m_dates
        context["monthly_sales"] = m_sales
        context["monthly_purchases"] = m_purch
        context["monthly_production"] = m_prod
        # compute pending amounts for this product
        # sales pending: sum of quantities not yet shipped
        sales_qs = SalesOrderLine.objects.filter(
            product__product=inv.product,
            complete=False,
        )
        context["sales_pending"] = (
            sales_qs.aggregate(total=Sum(F("quantity") - F("quantity_shipped")))[
                "total"
            ]
            or 0
        )
        # purchase pending: sum of remaining quantity to receive
        po_qs = PurchaseOrderLine.objects.filter(
            product__product=inv.product,
            complete=False,
        )
        context["purchase_pending"] = (
            po_qs.aggregate(total=Sum(F("quantity") - F("quantity_received")))["total"]
            or 0
        )
        # production pending: sum of remaining production quantity
        prod_qs = Production.objects.filter(
            product=inv.product,
            closed=False,
        ).filter(quantity__gt=F("quantity_received"))
        context["production_pending"] = (
            prod_qs.aggregate(total=Sum(F("quantity") - F("quantity_received")))[
                "total"
            ]
            or 0
        )

        # shortage: how much demand exceeds all available + incoming supply
        available = (
            inv.quantity + context["purchase_pending"] + context["production_pending"]
        )
        context["required_qty"] = max(0, context["sales_pending"] - available)

        # ── Stock location allocation ──
        context["allocated_qty"] = (
            inv.stock_locations.aggregate(total=Sum("quantity"))["total"] or 0
        )
        context["unallocated_qty"] = inv.quantity - context["allocated_qty"]
        context["ledger_has_locations"] = inv.product.inventory_ledger.filter(
            location__isnull=False
        ).exists()

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

    def get_inventory(self):
        return Inventory.objects.select_related("product").get(pk=self.kwargs.get("pk"))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["inventory"] = self.get_inventory()
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        inventory = self.get_inventory()
        initial["product"] = inventory.product
        return initial

    def get_form(self, *args, **kwargs):
        form = super().get_form(*args, **kwargs)
        form.fields["product"].disabled = True
        if "complete" in form.fields:
            del form.fields["complete"]
        return form

    def form_valid(self, form):
        inventory = self.get_inventory()
        form.instance.product = inventory.product
        form.instance.complete = True
        location = form.cleaned_data.get("location")

        # save the adjustment (updates Inventory.quantity and ledger)
        response = super().form_valid(form)

        # if a location was selected, route the delta to that bin
        if location:
            qty_delta = form.instance.quantity
            inv_loc, _ = InventoryLocation.objects.get_or_create(
                inventory=inventory,
                location=location,
                defaults={"quantity": 0},
            )
            inv_loc.quantity = max(inv_loc.quantity + qty_delta, 0)
            inv_loc.save()

            # tag the ledger entry with the location
            from .models import InventoryLedger

            entry = (
                InventoryLedger.objects.filter(
                    product=inventory.product,
                    action="Inventory Adjustment",
                    location__isnull=True,
                )
                .order_by("-date")
                .first()
            )
            if entry:
                entry.location = location
                entry.save(update_fields=["location"])

        return response

    def get_success_url(self):
        return reverse_lazy("inventory:inventory-detail", args=[self.kwargs.get("pk")])


class InventoryDashboardView(TemplateView):
    """Dashboard showing inventory metrics for the inventory app."""

    template_name = "inventory/inventory_dashboard.html"

    def get_context_data(self, **kwargs):
        from datetime import timedelta

        from django.db.models import (
            DecimalField,
            F,
            Min,
            OuterRef,
            Q,
            Subquery,
            Sum,
            Value,
        )
        from django.db.models.functions import Coalesce
        from django.utils import timezone
        from procurement.models import SupplierProduct
        from production.models import BillOfMaterials, BOMItem

        context = super().get_context_data(**kwargs)
        context["total_products"] = Product.objects.count()
        context["total_inventory_items"] = Inventory.objects.count()
        context["total_quantity"] = (
            Inventory.objects.aggregate(total=Sum("quantity"))["total"] or 0
        )

        # compute monetary stock value using min supplier cost per product
        min_cost_sq = (
            SupplierProduct.objects.filter(product=OuterRef("product"))
            .values("product")
            .annotate(mc=Min("cost"))
            .values("mc")[:1]
        )
        inventories = list(
            Inventory.objects.annotate(
                unit_cost=Subquery(min_cost_sq, output_field=DecimalField()),
            ).values_list("product_id", "quantity", "unit_cost")
        )

        # for products without a supplier cost, fall back to BOM component costs
        no_cost_ids = [pid for pid, qty, cost in inventories if cost is None and qty]
        bom_costs = {}
        if no_cost_ids:
            bom_items = (
                BOMItem.objects.filter(bom__product_id__in=no_cost_ids)
                .annotate(
                    comp_cost=Subquery(
                        SupplierProduct.objects.filter(product=OuterRef("product"))
                        .values("product")
                        .annotate(mc=Min("cost"))
                        .values("mc")[:1],
                        output_field=DecimalField(),
                    )
                )
                .values_list("bom__product_id", "quantity", "comp_cost")
            )
            for parent_id, bom_qty, comp_cost in bom_items:
                if comp_cost is not None:
                    bom_costs[parent_id] = (
                        bom_costs.get(parent_id, 0) + bom_qty * comp_cost
                    )

        stock_value = sum(
            qty * (cost if cost is not None else bom_costs.get(pid, 0))
            for pid, qty, cost in inventories
        )
        context["stock_value"] = stock_value

        # count of products below required stock level
        context["low_stock_count"] = Inventory.objects.filter(
            required_cached__gt=0
        ).count()

        total_products = context["total_products"]
        context["low_stock_percentage"] = (
            round(context["low_stock_count"] / total_products * 100)
            if total_products
            else 0
        )

        # top 5 most-needed low stock items — enriched with fill_pct for progress bars
        raw_low_stock = list(
            Inventory.objects.select_related("product")
            .filter(required_cached__gt=0)
            .order_by("-required_cached")[:5]
        )
        enriched_low_stock = []
        for _item in raw_low_stock:
            _denom = _item.quantity + _item.required_cached
            _fill = round(_item.quantity / _denom * 100) if _denom else 0
            enriched_low_stock.append(
                {
                    "pk": _item.pk,
                    "product": _item.product,
                    "quantity": _item.quantity,
                    "required_cached": _item.required_cached,
                    "fill_pct": _fill,
                }
            )
        context["top_low_stock_items"] = enriched_low_stock

        # 30-day stock movement from ledger
        cutoff_30d = timezone.now() - timedelta(days=30)
        ledger_30d = InventoryLedger.objects.filter(date__gte=cutoff_30d).aggregate(
            stock_in=Sum("quantity", filter=Q(quantity__gt=0)),
            stock_out=Sum("quantity", filter=Q(quantity__lt=0)),
        )
        context["stock_in_30d"] = ledger_30d["stock_in"] or 0
        context["stock_out_30d"] = abs(ledger_30d["stock_out"] or 0)

        # dead stock: products with quantity > 0, no demand, no ledger activity in 90 days
        cutoff_90d = timezone.now() - timedelta(days=90)
        active_product_ids = (
            InventoryLedger.objects.filter(date__gte=cutoff_90d)
            .values_list("product_id", flat=True)
            .distinct()
        )
        context["dead_stock_count"] = (
            Inventory.objects.filter(quantity__gt=0, required_cached=0)
            .exclude(product_id__in=active_product_ids)
            .count()
        )

        # stock health buckets for donut chart (mutually exclusive, priority-ordered)
        context["chart_low_stock"] = context["low_stock_count"]
        context["chart_zero_stock"] = Inventory.objects.filter(
            quantity=0, required_cached=0
        ).count()
        context["chart_dead_stock"] = context["dead_stock_count"]
        context["chart_healthy"] = max(
            0,
            total_products
            - context["chart_low_stock"]
            - context["chart_zero_stock"]
            - context["chart_dead_stock"],
        )

        # trend arrows: compare last 30d vs prior 30d for movement metrics
        cutoff_60d = timezone.now() - timedelta(days=60)
        ledger_prev = InventoryLedger.objects.filter(
            date__gte=cutoff_60d, date__lt=cutoff_30d
        ).aggregate(
            stock_in=Sum("quantity", filter=Q(quantity__gt=0)),
            stock_out=Sum("quantity", filter=Q(quantity__lt=0)),
        )
        prev_in = ledger_prev["stock_in"] or 0
        prev_out = abs(ledger_prev["stock_out"] or 0)

        def _trend(cur, prev):
            if cur > prev:
                return "up"
            if cur < prev:
                return "down"
            return "neutral"

        context["trend_stock_in"] = _trend(context["stock_in_30d"], prev_in)
        context["trend_stock_out"] = _trend(context["stock_out_30d"], prev_out)

        # net 7-day movement for total stock trend arrow
        net_7d = (
            InventoryLedger.objects.filter(
                date__gte=timezone.now() - timedelta(days=7)
            ).aggregate(net=Sum("quantity"))["net"]
            or 0
        )
        context["trend_quantity"] = (
            "up" if net_7d > 0 else ("down" if net_7d < 0 else "neutral")
        )

        # when ?required=1 is passed, include low-stock items in context
        if getattr(self, "request", None) and self.request.GET.get("required"):
            from procurement.services import (
                best_supplier_products,
                pending_po_by_product,
            )
            from production.services import bom_product_ids, pending_jobs_by_product

            inv_list = list(
                Inventory.objects.select_related("product").filter(
                    required_cached__gt=0
                )
            )
            product_ids = [inv.product_id for inv in inv_list]
            po_map = pending_po_by_product(product_ids)
            job_map = pending_jobs_by_product(product_ids)
            bom_ids = bom_product_ids(product_ids)
            supplier_map = best_supplier_products(product_ids)

            items = []
            for inv in inv_list:
                required_qty = inv.required_cached
                if required_qty <= 0:
                    continue
                prod_amount = job_map.get(inv.product_id, 0)
                po_amount = po_map.get(inv.product_id, 0)
                needed_po = max(required_qty - po_amount, 0)
                supplierproduct = supplier_map.get(inv.product_id)
                supplier_id = supplierproduct.supplier_id if supplierproduct else None
                has_bom = inv.product_id in bom_ids
                items.append(
                    {
                        "product": inv.product,
                        "required": required_qty,
                        "quantity": inv.quantity,
                        "production_amount": prod_amount,
                        "po_amount": po_amount,
                        "has_bom": has_bom,
                        "supplier_id": supplier_id,
                    }
                )
            context["required_items"] = items

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
            Inventory.objects.select_related("product").filter(required_cached__gt=0)
        )
        product_ids = [inv.product_id for inv in inv_list]

        po_map = pending_po_by_product(product_ids)
        job_map = pending_jobs_by_product(product_ids)
        bom_ids = bom_product_ids(product_ids)
        supplier_map = best_supplier_products(product_ids)

        items = []
        supplier_items: dict[int, list[tuple[int, int]]] = {}

        for inv in inv_list:
            # use cached value to avoid per-product N+1 queries
            required_qty = inv.required_cached
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

            items.append(
                {
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
                }
            )

        # apply filter: 'purchasable' = has a supplier and not fully covered by open POs
        # 'producible' = has a BOM and not fully covered by active production jobs
        filter_by = self.request.GET.get("filter", "")
        if filter_by == "purchasable":
            items = [
                e
                for e in items
                if e["supplier_id"] is not None and e["po_amount"] < e["required"]
            ]
        elif filter_by == "producible":
            items = [
                e
                for e in items
                if e["has_bom"] and e["production_amount"] < e["required"]
            ]
        context["filter_by"] = filter_by

        # sort items by requirement descending so highest shortages appear first
        items.sort(key=lambda ent: ent["required"], reverse=True)
        # generate purchase-order URLs for each entry that has a supplier
        for entry in items:
            sid = entry.get("supplier_id")
            if sid is not None and entry.get("can_order", False):
                pairs = supplier_items.get(sid, [])
                qs = "&".join(f"item={pid}:{qty}" for pid, qty in pairs)
                entry["po_url"] = (
                    f"{reverse('procurement:purchase-order-create')}?supplier={sid}&{qs}"
                )
            else:
                entry["po_url"] = None

        # paginate the results
        page = self.request.GET.get("page")
        paginator = Paginator(items, 20)
        context["required_items"] = paginator.get_page(page)
        return context

    def form_valid(self, form):
        inventory = Inventory.objects.select_related("product").get(
            pk=self.kwargs.get("pk")
        )
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
            data.append(
                {
                    "product": inv.product.name,
                    "quantity": inv.quantity,
                    "required": inv.required_cached,
                }
            )
        return JsonResponse(data, safe=False)


# ── Location CRUD ──────────────────────────────────────────────


class LocationListView(ListView):
    model = Location
    template_name = "inventory/location_list.html"
    context_object_name = "locations"

    def get_queryset(self):
        return Location.objects.filter(parent=None).prefetch_related(
            "children", "children__children"
        )


class LocationCreateView(CreateView):
    model = Location
    form_class = LocationForm
    template_name = "inventory/location_form.html"
    success_url = reverse_lazy("inventory:location-list")

    def get_initial(self):
        initial = super().get_initial()
        parent_pk = self.request.GET.get("parent")
        if parent_pk:
            initial["parent"] = parent_pk
        return initial


class LocationUpdateView(UpdateView):
    model = Location
    form_class = LocationForm
    template_name = "inventory/location_form.html"
    success_url = reverse_lazy("inventory:location-list")


class LocationDeleteView(DeleteView):
    model = Location
    template_name = "inventory/location_confirm_delete.html"
    success_url = reverse_lazy("inventory:location-list")


# ── Stock location assignment ──────────────────────────────────


class InventoryLocationCreateView(CreateView):
    model = InventoryLocation
    form_class = InventoryLocationForm
    template_name = "inventory/inventory_location_form.html"

    def get_inventory(self):
        return Inventory.objects.select_related("product").get(pk=self.kwargs["pk"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["inventory"] = self.get_inventory()
        return kwargs

    def form_valid(self, form):
        form.instance.inventory = self.get_inventory()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("inventory:inventory-detail", args=[self.kwargs["pk"]])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["inventory"] = self.get_inventory()
        return context


class InventoryLocationUpdateView(UpdateView):
    model = InventoryLocation
    form_class = InventoryLocationForm
    template_name = "inventory/inventory_location_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["inventory"] = self.object.inventory
        return kwargs

    def get_success_url(self):
        return reverse_lazy(
            "inventory:inventory-detail", args=[self.object.inventory.pk]
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["inventory"] = self.object.inventory
        return context


class InventoryLocationDeleteView(DeleteView):
    model = InventoryLocation
    template_name = "inventory/inventory_location_confirm_delete.html"

    def get_success_url(self):
        return reverse_lazy(
            "inventory:inventory-detail", args=[self.object.inventory.pk]
        )


class StockTransferCreateView(CreateView):
    model = StockTransfer
    form_class = StockTransferForm
    template_name = "inventory/stock_transfer_form.html"

    def get_inventory(self):
        return Inventory.objects.select_related("product").get(pk=self.kwargs["pk"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["inventory"] = self.get_inventory()
        return kwargs

    def get_form(self, *args, **kwargs):
        form = super().get_form(*args, **kwargs)
        form.instance.inventory = self.get_inventory()
        return form

    def form_valid(self, form):
        form.instance.inventory = self.get_inventory()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("inventory:inventory-detail", args=[self.kwargs["pk"]])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["inventory"] = self.get_inventory()
        return context


@method_decorator(csrf_exempt, name="dispatch")
class CatalogueApiView(View):
    """Public endpoint — returns catalogue products to paired instances."""

    def get(self, request, *args, **kwargs):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer "):
            return JsonResponse({"error": "Unauthorized"}, status=401)
        key = auth[len("Bearer ") :]
        if not any(
            hmac.compare_digest(key, pi.our_key) for pi in PairedInstance.objects.all()
        ):
            return JsonResponse({"error": "Unauthorized"}, status=401)
        products = Product.objects.filter(catalogue_item=True, sale_price__isnull=False)
        data = [
            {
                "name": p.name,
                "description": p.description,
                "sale_price": f"{p.sale_price:.2f}",
                "sku": None,
            }
            for p in products
        ]
        return JsonResponse(data, safe=False)
