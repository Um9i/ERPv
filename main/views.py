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
        # reuse inventory queryset for multiple stats and prefetch related product data
        # start with inventory queryset; prefetch related data needed for
        # cost calculations to avoid per-product queries
        inv_qs = (
            Inventory.objects.select_related("product")
            .prefetch_related(
                "product__product_suppliers",
                "product__billofmaterials__bom_items__product",
            )
            .all()
        )
        context["total_inventory"] = inv_qs.aggregate(total=Sum("quantity"))["total"] or 0
        # compute total inventory value without triggering unit_cost DB
        # queries by using prefetched relations and a local recursive helper
        def calc_cost(product, visited=None):
            if visited is None:
                visited = set()
            if product.pk in visited:
                return 0
            visited.add(product.pk)
            # cheapest supplier cost (use prefetched cache)
            suppliers = sorted(product.product_suppliers.all(), key=lambda s: s.cost)
            if suppliers:
                return suppliers[0].cost
            # no supplier; attempt BOM
            try:
                bom = product.billofmaterials
            except Product.billofmaterials.RelatedObjectDoesNotExist:
                return 0
            total = 0
            for item in bom.bom_items.all():
                total += item.quantity * calc_cost(item.product, visited)
            return total

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
        context["total_purchase_value"] = (
            PurchaseOrderLine.objects.aggregate(
                total=Sum(F("product__cost") * F("quantity"))
            )["total"]
            or 0
        )
        # total produced value (use quantity_received * cached cost helper)
        total_prod_val = 0
        for prod in Production.objects.select_related('product').all():
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
        po_vals = (
            PurchaseOrderLine.objects.filter(complete=False)
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
        supplier_ids = set(SupplierProduct.objects.values_list('product_id', flat=True))
        bom_ids = set(BillOfMaterials.objects.values_list('product_id', flat=True))
        # we already know producible count from the number of unique ids
        context["producible_count"] = len(bom_ids)
        # list of required inventory records (use cached field)
        req_qs = inv_qs.filter(required_cached__gt=0)
        required_items = []
        for inv in req_qs:
            req_amount = inv.required_cached
            if req_amount <= 0:
                continue
            pid = inv.product.pk
            pending_po = po_map.get(pid, 0)
            pending_job = job_map.get(pid, 0)
            has_job = pending_job > 0
            if pending_job >= req_amount:
                continue
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
