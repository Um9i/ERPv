from django.views.generic import TemplateView
from django.db.models import Sum, F


class DashboardView(TemplateView):
    template_name = "dashboard.html"

    def get_context_data(self, **kwargs):
        from inventory.models import Inventory, Product
        from sales.models import SalesOrderLine
        from procurement.models import PurchaseOrderLine, SupplierProduct
        from production.models import Production, BillOfMaterials

        context = super().get_context_data(**kwargs)
        # reuse inventory queryset for multiple stats; we'll use the
        # resulting product list as the seed for a broader graph walk that
        # gathers all products referenced by BOMs.  By computing a full set of
        # product ids up front we can eagerly load supplier cost rows and BOM
        # objects in a couple of queries instead of repeatedly hitting the
        # database during recursive cost computation.
        inv_qs = (
            Inventory.objects.select_related("product").all()
        )

        # also grab any products directly appearing on production rows; these
        # may not be present in inventory yet but still need cost data.
        prod_qs = Production.objects.select_related("product").all()

        # build closure of all products reachable via BOM relationships
        product_ids = set(inv_qs.values_list("product_id", flat=True))
        product_ids.update(prod_qs.values_list("product_id", flat=True))
        # breadth‑first traverse BOM graph
        from production.models import BOMItem
        queue = list(product_ids)
        while queue:
            pid = queue.pop()
            for item in BOMItem.objects.filter(bom__product_id=pid).select_related("product"):
                cid = item.product_id
                if cid not in product_ids:
                    product_ids.add(cid)
                    queue.append(cid)

        # fetch all supplier entries once
        supplier_map: dict[int, list] = {}
        # also keep reverse map from supplierproduct id -> product id
        sp_to_prod: dict[int, int] = {}
        from procurement.models import SupplierProduct
        for sp in SupplierProduct.objects.filter(product_id__in=product_ids).order_by("cost"):
            supplier_map.setdefault(sp.product_id, []).append(sp)
            sp_to_prod[sp.pk] = sp.product_id

        # fetch all BOM objects with their items -> convert to dict for O(1)
        bom_map = {
            b.product_id: b
            for b in BillOfMaterials.objects.filter(product_id__in=product_ids)
            .prefetch_related("bom_items__product")
        }

        context["total_inventory"] = inv_qs.aggregate(total=Sum("quantity"))["total"] or 0
        # compute total inventory value without triggering unit_cost DB
        # queries by using local recursive helper plus the preloaded maps
        def calc_cost(product, visited=None):
            if visited is None:
                visited = set()
            if product.pk in visited:
                return 0
            visited.add(product.pk)

            # cheapest supplier cost (use our pre‑built map)
            suppliers = supplier_map.get(product.pk, [])
            if suppliers:
                return suppliers[0].cost

            # no supplier; attempt BOM via map
            bom = bom_map.get(product.pk)
            if not bom:
                return 0
            total = 0
            for item in bom.bom_items.all():
                total += item.quantity * calc_cost(item.product, visited)
            return total
        context["total_inventory"] = inv_qs.aggregate(total=Sum("quantity"))["total"] or 0
        # compute total inventory value without triggering unit_cost DB
        # queries by using prefetched relations and a local recursive helper
        # memoization dictionary keyed by product.pk.  Without this we would
        # recompute costs for the same product repeatedly when iterating over
        # inventory or production rows; the recursion itself doesn't hit the
        # database thanks to prefetch_related, but eliminating duplicate
        # work reduces overall CPU and simplifies reasoning about the cost
        # graph.  See task earlier about dashboard optimization.
        cost_cache: dict[int, float] = {}

        def calc_cost(product, visited=None):
            # check memo first
            if product.pk in cost_cache:
                return cost_cache[product.pk]

            if visited is None:
                visited = set()
            if product.pk in visited:
                return 0
            visited.add(product.pk)
            # cheapest supplier cost (use prefetched cache)
            suppliers = sorted(product.product_suppliers.all(), key=lambda s: s.cost)
            if suppliers:
                cost = suppliers[0].cost
            else:
                # no supplier; attempt BOM
                try:
                    bom = product.billofmaterials
                except Product.billofmaterials.RelatedObjectDoesNotExist:
                    cost = 0
                else:
                    total = 0
                    for item in bom.bom_items.all():
                        total += item.quantity * calc_cost(item.product, visited)
                    cost = total
            cost_cache[product.pk] = cost
            return cost

        context["total_inventory_value"] = sum(
            inv.quantity * calc_cost(inv.product) for inv in inv_qs
        )
        context["product_count"] = inv_qs.count()
        # producible items count – we can determine this once we fetch
        # all BOM product ids below, avoiding a separate COUNT query.
        # (bom_ids variable declared later)
        context["producible_count"] = 0  # will set after bom_ids computed

        # open counts for orders and jobs
        context["open_sales_count"] = SalesOrderLine.objects.filter(complete=False).count()
        context["open_purchase_count"] = PurchaseOrderLine.objects.filter(complete=False).count()
        context["open_production_count"] = Production.objects.filter(closed=False).count()

        # procurement metrics
        from procurement.models import PurchaseOrder, Supplier
        context["total_purchase_orders"] = PurchaseOrder.objects.count()
        context["pending_receiving"] = PurchaseOrderLine.objects.filter(complete=False).count()
        context["lines_received"] = PurchaseOrderLine.objects.filter(complete=True).count()
        context["total_suppliers"] = Supplier.objects.count()

        # sales metrics
        from sales.models import SalesOrder, Customer
        context["total_orders"] = SalesOrder.objects.count()
        context["shipped_orders"] = SalesOrderLine.objects.filter(quantity_shipped__gt=0).count()
        context["pending_shipping"] = context["open_sales_count"]
        context["total_customers"] = Customer.objects.count()
        context["total_sales_value"] = SalesOrderLine.objects.aggregate(
            total=Sum(F("product__price") * F("quantity"))
        )["total"] or 0
        # compare to last month
        from django.utils import timezone
        from datetime import timedelta
        today = timezone.now().date()
        this_month_start = today.replace(day=1)
        prev_month_end = this_month_start - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)
        sales_this_month = SalesOrderLine.objects.filter(
            sales_order__created_at__date__gte=this_month_start,
            sales_order__created_at__date__lt=(this_month_start + timedelta(days=32)).replace(day=1)
        ).aggregate(total=Sum(F("product__price") * F("quantity")))["total"] or 0
        sales_prev_month = SalesOrderLine.objects.filter(
            sales_order__created_at__date__gte=prev_month_start,
            sales_order__created_at__date__lte=prev_month_end
        ).aggregate(total=Sum(F("product__price") * F("quantity")))["total"] or 0
        context["sales_this_month"] = float(sales_this_month)
        context["sales_prev_month"] = float(sales_prev_month)
        if sales_prev_month:
            context["sales_change_pct"] = float((sales_this_month - sales_prev_month) / sales_prev_month * 100)
        else:
            context["sales_change_pct"] = None
        # year-over-year comparison (same month last year)
        prev_year_start = this_month_start.replace(year=this_month_start.year - 1)
        prev_year_end = prev_year_start.replace(day=1) + timedelta(days=32)
        prev_year_end = prev_year_end.replace(day=1) - timedelta(days=1)
        sales_last_year = SalesOrderLine.objects.filter(
            sales_order__created_at__date__gte=prev_year_start,
            sales_order__created_at__date__lte=prev_year_end
        ).aggregate(total=Sum(F("product__price") * F("quantity")))["total"] or 0
        context["sales_last_year"] = float(sales_last_year)
        if sales_last_year:
            context["sales_yoy_pct"] = float((sales_this_month - sales_last_year) / sales_last_year * 100)
        else:
            context["sales_yoy_pct"] = None
        # monthly target (could be set via settings)
        from django.conf import settings
        context["sales_target"] = getattr(settings, "SALES_TARGET_MONTHLY", None)
        if context["sales_target"]:
            context["sales_vs_target_pct"] = float((sales_this_month - context["sales_target"]) / context["sales_target"] * 100)
        else:
            context["sales_vs_target_pct"] = None
        # compute total purchase value from supplier_map instead of
        # performing another SQL join.  fall back to zero if supplier
        # information is missing.
        total_purchase_value = 0
        for line in PurchaseOrderLine.objects.all():
            sp_id = line.product_id
            suppliers_for_line = supplier_map.get(sp_id) or []
            if suppliers_for_line:
                total_purchase_value += suppliers_for_line[0].cost * line.quantity
        context["total_purchase_value"] = total_purchase_value
        # total produced value (use quantity_received * cached cost helper).
        # we fetch productions with the same prefetch pattern so that
        # products appearing only in production jobs also participate in our
        # prefetch cache and avoid per-product queries in calc_cost.
        total_prod_val = 0
        prod_qs = (
            Production.objects.select_related('product')
            .prefetch_related(
                "product__product_suppliers",
                "product__billofmaterials__bom_items__product",
                "product__billofmaterials__bom_items__product__product_suppliers",
            )
            .all()
        )
        for prod in prod_qs:
            total_prod_val += prod.quantity_received * calc_cost(prod.product)
        context["total_production_value"] = total_prod_val
        # executive summary metrics
        context["executive"] = {
            "total_sales": context["total_sales_value"],
            "open_orders": context.get("open_sales_count", 0),
            "inventory_value": context.get("total_inventory_value", 0),
            "active_jobs": context.get("open_production_count", 0),
        }
        # attention required counts
        context["attention"] = {
            "pending_shipping": context.get("pending_shipping", 0),
            "open_production": context.get("open_production_count", 0),
            "open_pos": context.get("open_purchase_count", 0),
            # low_stock count (number of products with shortage)
            # will update after required_list computed
            "low_stock": 0,
        }
        # inventory breakdown (quantity by product name) – we can reuse
        # the same queryset we prefetched earlier
        context["inventory_breakdown_labels"] = [inv.product.name for inv in inv_qs]
        # show only current quantities
        context["inventory_breakdown_data"] = [inv.quantity for inv in inv_qs]
        # sales time series for multiple ranges – aggregate once
        from django.utils import timezone
        from django.db.models.functions import TruncDate
        from datetime import timedelta
        today = timezone.now().date()
        start_window = today - timedelta(days=89)
        grouped = (
            SalesOrderLine.objects
            .annotate(day=TruncDate('sales_order__created_at'))
            .filter(sales_order__created_at__date__gte=start_window)
            .values('day')
            .annotate(total=Sum(F('product__price') * F('quantity')))
        )
        day_totals = {r['day']: r['total'] for r in grouped}
        labels_90 = [(today - timedelta(days=i)).isoformat() for i in range(89, -1, -1)]
        data_90 = [float(day_totals.get(today - timedelta(days=i), 0)) for i in range(89, -1, -1)]
        context["sales_over_time_labels_90"] = labels_90
        context["sales_over_time_data_90"] = data_90
        context["sales_over_time_labels"] = labels_90[-30:]
        context["sales_over_time_data"] = data_90[-30:]
        context["sales_over_time_labels_7"] = labels_90[-7:]
        context["sales_over_time_data_7"] = data_90[-7:]
        # metrics (average and max) for each window
        def metrics(arr):
            if arr:
                return {"avg": sum(arr)/len(arr), "max": max(arr)}
            return {"avg": 0, "max": 0}
        context["sales_metrics_90"] = metrics(data_90)
        context["sales_metrics_30"] = metrics(data_90[-30:])
        context["sales_metrics_7"] = metrics(data_90[-7:])
        # simple comparison bar for total purchase vs sales value
        context["purchase_sales_labels"] = ["Purchase Value", "Sales Value"]
        context["purchase_sales_data"] = [
            float(context["total_purchase_value"]),
            float(context["total_sales_value"]),
        ]
        # total required shortage across inventory using cached field
        from inventory.models import Inventory
        # total required shortage across inventory using cached field
        # reuse inv_qs rather than hitting the table again
        context["total_required"] = (
            inv_qs.aggregate(total=Sum('required_cached'))['total'] or 0
        )
        # prepare lookup maps for purchase orders and production jobs
        # pending quantities by underlying product; first aggregate by
        # supplierproduct id, then translate via supplier_map to the real
        # product id without another join.
        po_vals = (
            PurchaseOrderLine.objects.filter(complete=False)
            .values('product')
            .annotate(total=Sum(F('quantity') - F('quantity_received')))
        )
        po_map = {}
        for v in po_vals:
            sp_id = v['product']
            total = v['total'] or 0
            prod_id = sp_to_prod.get(sp_id)
            if prod_id is not None:
                po_map[prod_id] = po_map.get(prod_id, 0) + total
        job_vals = (
            Production.objects.filter(closed=False)
            .annotate(rem=F('quantity') - F('quantity_received'))
            .values('product')
            .annotate(total=Sum('rem'))
        )
        job_map = {v['product']: v['total'] or 0 for v in job_vals}
        # precompute which products have suppliers or a BOM
        supplier_ids = set(SupplierProduct.objects.values_list('product_id', flat=True))
        bom_ids = set(BillOfMaterials.objects.values_list('product_id', flat=True))
        # we already know producible count from the number of unique ids
        context["producible_count"] = len(bom_ids)
        # list of required inventory records; compute live using property
        required_items = []
        for inv in inv_qs:
            # use live calculation rather than cached to stay consistent with
            # the low-stock view.  update cache while we're here so both stay
            # in sync for performance elsewhere.
            req_amount = inv.required
            if req_amount <= 0:
                # if cached is stale, reset it
                if inv.required_cached != 0:
                    inv.required_cached = 0
                    inv.save(update_fields=["required_cached"])
                continue
            # save cache in case it changed
            if inv.required_cached != req_amount:
                inv.required_cached = req_amount
                inv.save(update_fields=["required_cached"])

            pid = inv.product.pk
            pending_po = po_map.get(pid, 0)
            pending_job = job_map.get(pid, 0)
            has_job = pending_job > 0
            # do not drop items simply because there are open jobs; keep
            # dashboard count in sync with the low-stock list
            inv._pending_po = pending_po
            inv._pending_job = pending_job
            inv._has_job = has_job
            inv._can_purchase = pid in supplier_ids
            inv._can_produce = pid in bom_ids
            required_items.append(inv)
        # sort descending by cached requirement
        required_items.sort(key=lambda i: i.required_cached, reverse=True)
        # build simple data for template (limit to top 5)
        context["required_list"] = [
            {
                "inventory": inv,
                "can_purchase": getattr(inv, '_can_purchase', False),
                "can_produce": getattr(inv, '_can_produce', False),
                # expose pending info for template
                "pending_po": getattr(inv, "_pending_po", 0),
                "pending_job": getattr(inv, "_pending_job", 0),
                "has_job": getattr(inv, "_has_job", False),
            }
            for inv in required_items[:5]
        ]
        # now that required_list exists update attention low_stock and detail list
        context["attention"]["low_stock"] = len(context["required_list"])
        context["low_stock_items"] = [
            {"id": item["inventory"].product.pk, "name": item["inventory"].product.name, "required": item["inventory"].required_cached}
            for item in context["required_list"]
        ]
        # low_stock_target no longer needed; dropdown will list all items
        # (context["low_stock_items"] already computed above)
        # pending quantities
        context["sales_pending_qty"] = (
            SalesOrderLine.objects.filter(complete=False)
            .aggregate(total=Sum(F("quantity") - F("quantity_shipped")))["total"]
            or 0
        )
        context["purchase_pending_qty"] = (
            PurchaseOrderLine.objects.filter(complete=False)
            .aggregate(total=Sum(F("quantity") - F("quantity_received")))["total"]
            or 0
        )
        context["production_pending_qty"] = (
            Production.objects.filter(closed=False)
            .aggregate(total=Sum(F("quantity") - F("quantity_received")))["total"]
            or 0
        )
        return context
