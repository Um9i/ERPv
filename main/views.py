from django.views.generic import TemplateView
from django.db.models import Sum, F


class DashboardView(TemplateView):
    template_name = "dashboard.html"

    def get_context_data(self, **kwargs):
        from inventory.models import Inventory
        from sales.models import SalesOrderLine
        from procurement.models import PurchaseOrderLine
        from production.models import Production

        context = super().get_context_data(**kwargs)
        # overall inventory on hand
        context["total_inventory"] = (
            Inventory.objects.aggregate(total=Sum("quantity"))["total"] or 0
        )
        # basic counts
        context["product_count"] = Inventory.objects.count()
        # products with a bill of materials (producible items)
        from production.models import BillOfMaterials
        context["producible_count"] = BillOfMaterials.objects.count()
        context["open_sales_count"] = SalesOrderLine.objects.filter(complete=False).count()
        context["open_purchase_count"] = PurchaseOrderLine.objects.filter(complete=False).count()
        context["open_production_count"] = Production.objects.filter(closed=False).count()
        # procurement dashboard metrics
        from procurement.models import PurchaseOrder, Supplier
        context["total_purchase_orders"] = PurchaseOrder.objects.count()
        context["pending_receiving"] = PurchaseOrderLine.objects.filter(complete=False).count()
        context["lines_received"] = PurchaseOrderLine.objects.filter(complete=True).count()
        context["total_suppliers"] = Supplier.objects.count()
        # sales dashboard metrics
        from sales.models import SalesOrder, Customer
        context["total_orders"] = SalesOrder.objects.count()
        context["shipped_orders"] = SalesOrderLine.objects.filter(quantity_shipped__gt=0).count()
        context["pending_shipping"] = SalesOrderLine.objects.filter(complete=False).count()
        context["total_customers"] = Customer.objects.count()
        # total required shortage across inventory
        from inventory.models import Inventory
        # cannot aggregate property so compute in Python loop
        context["total_required"] = sum(inv.required for inv in Inventory.objects.all())
        # list of required products for dashboard
        req_qs = Inventory.objects.filter(product__isnull=False)
        # annotate required property by evaluating per object
        # only include inventories where a shortage exists and no open
        # production job already covers the product (since that job will
        # satisfy the requirement).
        required_items = []
        for inv in req_qs:
            if inv.required <= 0:
                continue
            # compute pending purchase order quantity
            po_qs = PurchaseOrderLine.objects.filter(
                product__product=inv.product,
                complete=False,
            )
            pending_po = po_qs.aggregate(
                total=Sum(F("quantity") - F("quantity_received"))
            )["total"] or 0
            # calculate pending production quantity (unreceived) and whether any job exists
            from production.models import Production
            job_qs = Production.objects.filter(
                product=inv.product,
                closed=False,
            )
            pending_job = job_qs.aggregate(
                total=Sum(F('quantity') - F('quantity_received'))
            )["total"] or 0
            has_job = pending_job > 0
            # if jobs already cover the required shortage, skip item entirely
            if pending_job >= inv.required:
                continue
            # always include inventory item but also record pending amounts
            inv._pending_po = pending_po
            inv._pending_job = pending_job
            inv._has_job = has_job
            required_items.append(inv)
        # sort descending by required need
        required_items.sort(key=lambda i: i.required, reverse=True)
        # build simple data for template (limit to top 5)
        context["required_list"] = [
            {
                "inventory": inv,
                "can_purchase": inv.product.product_suppliers.exists(),
                "can_produce": hasattr(inv.product, "billofmaterials"),
                # expose pending info for template
                "pending_po": getattr(inv, "_pending_po", 0),
                "pending_job": getattr(inv, "_pending_job", 0),
                "has_job": getattr(inv, "_has_job", False),
            }
            for inv in required_items[:5]
        ]
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
