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
        # inventory and production querysets.  we defer expensive cost
        # lookups to a helper that uses pre‑fetched maps below instead of
        # relying on Django prefetch_related; this keeps supplierproduct
        # table access to a single query which is important for our
        # query‑count test.
        inv_qs = Inventory.objects.select_related("product").all()
        prod_qs = Production.objects.select_related("product").all()

        # build closure of all products reachable via BOM relationships so we
        # can preload supplier costs and BOMs just once.  this replicates the
        # earlier logic but remains relatively cheap.
        product_ids = set(inv_qs.values_list("product_id", flat=True))
        product_ids.update(prod_qs.values_list("product_id", flat=True))
        from production.models import BOMItem
        queue = list(product_ids)
        while queue:
            pid = queue.pop()
            for item in BOMItem.objects.filter(bom__product_id=pid).select_related("product"):
                cid = item.product_id
                if cid not in product_ids:
                    product_ids.add(cid)
                    queue.append(cid)

        # fetch all supplier entries once and keep reverse map for purchase
        # order quantity lookups later.
        supplier_map: dict[int, list] = {}
        sp_to_prod: dict[int, int] = {}
        from procurement.models import SupplierProduct
        for sp in SupplierProduct.objects.filter(product_id__in=product_ids).order_by("cost"):
            supplier_map.setdefault(sp.product_id, []).append(sp)
            sp_to_prod[sp.pk] = sp.product_id

        # also fetch BOM objects with related items for our cost helper
        bom_map = {
            b.product_id: b
            for b in BillOfMaterials.objects.filter(product_id__in=product_ids)
            .prefetch_related("bom_items__product")
        }

        # memoization cache for recursive cost computation
        cost_cache: dict[int, float] = {}

        def calc_cost(product, visited=None):
            if product.pk in cost_cache:
                return cost_cache[product.pk]
            if visited is None:
                visited = set()
            if product.pk in visited:
                return 0
            visited.add(product.pk)

            # cheapest supplier cost (use supplier_map)
            suppliers = supplier_map.get(product.pk, [])
            if suppliers:
                cost = suppliers[0].cost
            else:
                bom = bom_map.get(product.pk)
                if not bom:
                    cost = 0
                else:
                    total = 0
                    for item in bom.bom_items.all():
                        total += item.quantity * calc_cost(item.product, visited)
                    cost = total
            cost_cache[product.pk] = cost
            return cost

        context["total_inventory"] = inv_qs.aggregate(total=Sum("quantity"))["total"] or 0
        context["total_inventory_value"] = sum(
            inv.quantity * calc_cost(inv.product) for inv in inv_qs
        )
        context["product_count"] = inv_qs.count()
        # producible items count – we can determine this once from the set of
        # BOM owners computed above
        context["producible_count"] = len({b.product_id for b in bom_map.values()})

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
        # total purchase value can be computed directly via a join on
        # the SupplierProduct.cost field.  this avoids manual loops and is
        # handled in the database efficiently.
        context["total_purchase_value"] = (
            PurchaseOrderLine.objects.aggregate(
                total=Sum(F("product__cost") * F("quantity"))
            )["total"]
            or 0
        )
        # total produced value (use quantity_received * cached cost helper).
        # use the prod_qs we built earlier; cost calculation will consult the
        # supplier_map so no additional supplierproduct queries are needed.
        context["total_production_value"] = sum(
            prod.quantity_received * calc_cost(prod.product) for prod in prod_qs
        )
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
        # pending quantities per product for open purchase order lines.
        # use select_related so we can group by the underlying Product id
        # without needing a separate mapping.
        po_vals = (
            PurchaseOrderLine.objects.filter(complete=False)
            .select_related('product__product')
            .values('product__product')
            .annotate(total=Sum(F('quantity') - F('quantity_received')))
        )
        po_map = {v['product__product']: v['total'] or 0 for v in po_vals}
        job_vals = (
            Production.objects.filter(closed=False)
            .annotate(rem=F('quantity') - F('quantity_received'))
            .values('product')
            .annotate(total=Sum('rem'))
        )
        job_map = {v['product']: v['total'] or 0 for v in job_vals}
        # precompute which products have suppliers or a BOM
        supplier_ids = set(supplier_map.keys())
        bom_ids = set(bom_map.keys())
        # producible count was already computed earlier but keep for safety
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
