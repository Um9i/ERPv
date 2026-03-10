import csv
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict

from django.db.models import DecimalField, Min, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce, TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView
from django.views.generic.dates import ArchiveIndexView, MonthArchiveView

from inventory.models import Inventory, Product
from procurement.models import PurchaseLedger, Supplier, SupplierProduct
from production.models import BOMItem
from sales.models import Customer, SalesLedger


class FinanceDashboardView(TemplateView):
    template_name = "finance/dashboard.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        sales_total = SalesLedger.objects.aggregate(
            total=Coalesce(Sum("value"), Decimal("0"))
        )["total"] or Decimal("0")
        purchase_total = PurchaseLedger.objects.aggregate(
            total=Coalesce(Sum("value"), Decimal("0"))
        )["total"] or Decimal("0")

        now = timezone.now()
        month_filter = {"date__year": now.year, "date__month": now.month}
        month_sales = SalesLedger.objects.filter(**month_filter).aggregate(
            total=Coalesce(Sum("value"), Decimal("0"))
        )["total"] or Decimal("0")
        month_purchases = PurchaseLedger.objects.filter(**month_filter).aggregate(
            total=Coalesce(Sum("value"), Decimal("0"))
        )["total"] or Decimal("0")

        # Monthly chart – past 12 months
        today = now.date()
        first_of_month = today.replace(day=1)
        chart_months = []
        for i in range(11, -1, -1):
            m = first_of_month.month - i
            y = first_of_month.year
            while m <= 0:
                m += 12
                y -= 1
            chart_months.append(date(y, m, 1))
        from_dt = timezone.make_aware(
            datetime(chart_months[0].year, chart_months[0].month, 1)
        )
        sales_monthly = (
            SalesLedger.objects.filter(date__gte=from_dt)
            .annotate(month=TruncMonth("date"))
            .values("month")
            .annotate(total=Sum("value"))
            .order_by("month")
        )
        purchases_monthly = (
            PurchaseLedger.objects.filter(date__gte=from_dt)
            .annotate(month=TruncMonth("date"))
            .values("month")
            .annotate(total=Sum("value"))
            .order_by("month")
        )
        sales_lu = {
            entry["month"].strftime("%Y-%m"): float(entry["total"])
            for entry in sales_monthly
        }
        purchases_lu = {
            entry["month"].strftime("%Y-%m"): float(entry["total"])
            for entry in purchases_monthly
        }
        month_labels = [m.strftime("%Y-%m") for m in chart_months]
        chart_data = {
            "months": month_labels,
            "sales": [sales_lu.get(m, 0) for m in month_labels],
            "purchases": [purchases_lu.get(m, 0) for m in month_labels],
        }

        # Stock value from inventory (min supplier cost, BOM fallback)
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

        context.update(
            {
                "now": now,
                "sales_total": sales_total,
                "purchase_total": purchase_total,
                "gross_profit": sales_total - purchase_total,
                "month_sales_total": month_sales,
                "month_purchase_total": month_purchases,
                "month_profit": month_sales - month_purchases,
                "recent_sales": SalesLedger.objects.select_related(
                    "customer", "product"
                ).order_by("-date")[:5],
                "recent_purchases": PurchaseLedger.objects.select_related(
                    "supplier", "product"
                ).order_by("-date")[:5],
                "chart_data": chart_data,
                "stock_value": stock_value,
            }
        )
        return context


class LedgerArchiveMixin:
    date_field = "date"
    date_list_period = "month"
    allow_future = False
    allow_empty = True
    paginate_by = 25
    month_format = "%m"
    make_object_list = True

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.setdefault("ledger_label", "Ledger")
        context.setdefault("today", timezone.now())
        return context


# ---------------------------------------------------------------------------
# Sales ledger
# ---------------------------------------------------------------------------


class SalesLedgerFilterMixin:
    """Shared queryset filtering for sales ledger views."""

    def get_queryset(self):
        qs = super().get_queryset().select_related("customer", "product")
        customer_id = self.request.GET.get("customer")
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        product_id = self.request.GET.get("product")
        if product_id:
            qs = qs.filter(product_id=product_id)
        return qs

    def _sales_context(self, context: dict) -> dict:
        context["ledger_label"] = "Sales Ledger"
        context["customers"] = Customer.objects.order_by("name")
        context["selected_customer"] = self.request.GET.get("customer", "")
        context["products"] = (
            Product.objects.filter(sales_ledger__isnull=False)
            .distinct()
            .order_by("name")
        )
        context["selected_product"] = self.request.GET.get("product", "")
        return context


class SalesLedgerArchiveView(
    SalesLedgerFilterMixin, LedgerArchiveMixin, ArchiveIndexView
):
    model = SalesLedger
    template_name = "finance/salesledger_archive.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        self._sales_context(context)
        # Total across all (filtered) results, not just current page
        qs = self.get_queryset()
        context["overall_total"] = qs.aggregate(
            total=Coalesce(Sum("value"), Decimal("0"))
        )["total"] or Decimal("0")
        context["page_total"] = sum(
            (e.value for e in context["object_list"]), Decimal("0")
        )
        return context


class SalesLedgerMonthArchiveView(
    SalesLedgerFilterMixin, LedgerArchiveMixin, MonthArchiveView
):
    model = SalesLedger
    template_name = "finance/salesledger_month.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        self._sales_context(context)
        # self.object_list is the month-filtered queryset before pagination
        context["month_total"] = self.object_list.aggregate(
            total=Coalesce(Sum("value"), Decimal("0"))
        )["total"] or Decimal("0")
        context["page_total"] = sum(
            (e.value for e in context["object_list"]), Decimal("0")
        )
        return context


# ---------------------------------------------------------------------------
# Purchase ledger
# ---------------------------------------------------------------------------


class PurchaseLedgerFilterMixin:
    """Shared queryset filtering for purchase ledger views."""

    def get_queryset(self):
        qs = super().get_queryset().select_related("supplier", "product")
        supplier_id = self.request.GET.get("supplier")
        if supplier_id:
            qs = qs.filter(supplier_id=supplier_id)
        return qs

    def _purchase_context(self, context: dict) -> dict:
        context["ledger_label"] = "Purchase Ledger"
        context["suppliers"] = Supplier.objects.order_by("name")
        context["selected_supplier"] = self.request.GET.get("supplier", "")
        return context


class PurchaseLedgerArchiveView(
    PurchaseLedgerFilterMixin, LedgerArchiveMixin, ArchiveIndexView
):
    model = PurchaseLedger
    template_name = "finance/purchaseledger_archive.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        self._purchase_context(context)
        qs = self.get_queryset()
        context["overall_total"] = qs.aggregate(
            total=Coalesce(Sum("value"), Decimal("0"))
        )["total"] or Decimal("0")
        context["page_total"] = sum(
            (e.value for e in context["object_list"]), Decimal("0")
        )
        return context


class PurchaseLedgerMonthArchiveView(
    PurchaseLedgerFilterMixin, LedgerArchiveMixin, MonthArchiveView
):
    model = PurchaseLedger
    template_name = "finance/purchaseledger_month.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        self._purchase_context(context)
        # self.object_list is the month-filtered queryset before pagination
        context["month_total"] = self.object_list.aggregate(
            total=Coalesce(Sum("value"), Decimal("0"))
        )["total"] or Decimal("0")
        context["page_total"] = sum(
            (e.value for e in context["object_list"]), Decimal("0")
        )
        return context


# ---------------------------------------------------------------------------
# CSV export views
# ---------------------------------------------------------------------------


class OutstandingOrdersView(TemplateView):
    template_name = "finance/outstanding_orders.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        from django.core.paginator import Paginator
        from django.db.models import DecimalField, F, OuterRef, Subquery
        from django.db.models.functions import Coalesce, Greatest

        from procurement.models import PurchaseOrder, PurchaseOrderLine
        from sales.models import SalesOrder, SalesOrderLine

        context = super().get_context_data(**kwargs)

        # Subquery: remaining value on a sales order (mirrors remaining_total property)
        so_open_value_sq = (
            SalesOrderLine.objects.filter(sales_order=OuterRef("pk"))
            .values("sales_order")
            .annotate(
                v=Sum(
                    F("product__price")
                    * Greatest(F("quantity") - F("quantity_shipped"), 0)
                )
            )
            .values("v")
        )
        open_sales_qs = (
            SalesOrder.objects.filter(sales_order_lines__complete=False)
            .distinct()
            .select_related("customer")
            .annotate(
                open_value=Coalesce(
                    Subquery(so_open_value_sq, output_field=DecimalField()),
                    Decimal("0"),
                )
            )
            .order_by("-open_value")
        )
        context["open_sales_value"] = open_sales_qs.aggregate(total=Sum("open_value"))[
            "total"
        ] or Decimal("0")
        sales_paginator = Paginator(open_sales_qs, 15)
        context["open_sales"] = sales_paginator.get_page(
            self.request.GET.get("sales_page")
        )

        # Subquery: remaining value on a purchase order (mirrors remaining_total property)
        po_open_value_sq = (
            PurchaseOrderLine.objects.filter(purchase_order=OuterRef("pk"))
            .values("purchase_order")
            .annotate(
                v=Sum(
                    F("product__cost")
                    * Greatest(F("quantity") - F("quantity_received"), 0)
                )
            )
            .values("v")
        )
        open_purchases_qs = (
            PurchaseOrder.objects.filter(purchase_order_lines__complete=False)
            .distinct()
            .select_related("supplier")
            .annotate(
                open_value=Coalesce(
                    Subquery(po_open_value_sq, output_field=DecimalField()),
                    Decimal("0"),
                )
            )
            .order_by("-open_value")
        )
        context["open_purchases_value"] = open_purchases_qs.aggregate(
            total=Sum("open_value")
        )["total"] or Decimal("0")
        po_paginator = Paginator(open_purchases_qs, 15)
        context["open_purchases"] = po_paginator.get_page(
            self.request.GET.get("po_page")
        )

        return context


class ProductPLView(TemplateView):
    template_name = "finance/product_pl.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        from django.db.models import DecimalField, OuterRef, Subquery

        from procurement.models import SupplierProduct

        context = super().get_context_data(**kwargs)

        # 1. Aggregate all sales data in a single GROUP BY query
        sales_data = SalesLedger.objects.values("product_id").annotate(
            total_qty=Sum("quantity"),
            total_revenue=Sum("value"),
        )
        sales_map = {row["product_id"]: row for row in sales_data}
        if not sales_map:
            context.update(
                rows=[],
                sort="",
                total_revenue=Decimal("0"),
                total_cost=Decimal("0"),
                total_profit=Decimal("0"),
                avg_margin_pct=None,
                chart_data={"labels": [], "values": [], "colors": []},
            )
            return context

        # 2. Cheapest supplier cost per product — single annotated query
        min_cost_subq = (
            SupplierProduct.objects.filter(product=OuterRef("pk"))
            .order_by("cost")
            .values("cost")[:1]
        )
        products = (
            Product.objects.filter(pk__in=sales_map.keys())
            .annotate(
                supplier_unit_cost=Subquery(min_cost_subq, output_field=DecimalField())
            )
            .select_related("product_inventory")
        )

        # 3. Build rows in Python — no per-product DB hits
        rows = []
        for product in products:
            data = sales_map[product.pk]
            unit_cost = Decimal(str(product.supplier_unit_cost or 0))
            sale_price = product.sale_price or Decimal("0")
            total_sold_qty = data["total_qty"] or 0
            total_revenue = data["total_revenue"] or Decimal("0")
            total_cost = Decimal(str(total_sold_qty)) * unit_cost
            gross_profit = total_revenue - total_cost
            margin = sale_price - unit_cost
            margin_pct = (
                float(gross_profit / total_revenue * 100) if total_revenue > 0 else None
            )
            inventory_pk = (
                product.product_inventory.pk
                if hasattr(product, "product_inventory") and product.product_inventory
                else None
            )
            rows.append(
                {
                    "product": product,
                    "inventory_pk": inventory_pk,
                    "unit_cost": unit_cost,
                    "sale_price": sale_price,
                    "margin": margin,
                    "margin_pct": margin_pct,
                    "total_sold_qty": total_sold_qty,
                    "total_revenue": total_revenue,
                    "total_cost": total_cost,
                    "gross_profit": gross_profit,
                }
            )

        sort = self.request.GET.get("sort", "")
        if sort == "margin_pct":
            rows.sort(
                key=lambda r: r["margin_pct"] if r["margin_pct"] is not None else -999,
                reverse=True,
            )
        elif sort == "revenue":
            rows.sort(key=lambda r: r["total_revenue"] or 0, reverse=True)
        else:
            rows.sort(key=lambda r: r["gross_profit"] or 0, reverse=True)

        total_revenue = sum((r["total_revenue"] for r in rows), Decimal("0"))
        total_cost = sum((r["total_cost"] for r in rows), Decimal("0"))
        total_profit = total_revenue - total_cost

        avg_margin_pct = None
        margin_values = [r["margin_pct"] for r in rows if r["margin_pct"] is not None]
        if margin_values:
            avg_margin_pct = sum(margin_values) / len(margin_values)

        top10 = sorted(rows, key=lambda r: r["gross_profit"] or 0, reverse=True)[:10]

        chart_data = {
            "labels": [r["product"].name for r in top10],
            "values": [float(r["gross_profit"]) for r in top10],
            "colors": [
                (
                    "#198754"
                    if (r["margin_pct"] or 0) >= 30
                    else "#ffc107" if (r["margin_pct"] or 0) >= 10 else "#dc3545"
                )
                for r in top10
            ],
        }

        context["rows"] = rows
        context["sort"] = sort
        context["total_revenue"] = total_revenue
        context["total_cost"] = total_cost
        context["total_profit"] = total_profit
        context["avg_margin_pct"] = avg_margin_pct
        context["chart_data"] = chart_data
        return context


class SalesLedgerExportView(View):
    def get(self, request):
        qs = SalesLedger.objects.select_related("customer", "product").order_by("-date")
        customer_id = request.GET.get("customer")
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        product_id = request.GET.get("product")
        if product_id:
            qs = qs.filter(product_id=product_id)
        year = request.GET.get("year")
        month = request.GET.get("month")
        if year and month:
            qs = qs.filter(date__year=year, date__month=month)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="sales_ledger.csv"'
        writer = csv.writer(response)
        writer.writerow(
            ["Date", "Customer", "Product", "Quantity", "Value", "Transaction"]
        )
        for entry in qs:
            writer.writerow(
                [
                    entry.date.strftime("%Y-%m-%d %H:%M"),
                    entry.customer.name,
                    entry.product.name,
                    entry.quantity,
                    entry.value,
                    f"SO{entry.transaction_id:05d}",
                ]
            )
        return response


class PurchaseLedgerExportView(View):
    def get(self, request):
        qs = PurchaseLedger.objects.select_related("supplier", "product").order_by(
            "-date"
        )
        supplier_id = request.GET.get("supplier")
        if supplier_id:
            qs = qs.filter(supplier_id=supplier_id)
        year = request.GET.get("year")
        month = request.GET.get("month")
        if year and month:
            qs = qs.filter(date__year=year, date__month=month)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="purchase_ledger.csv"'
        writer = csv.writer(response)
        writer.writerow(
            ["Date", "Supplier", "Product", "Quantity", "Value", "Transaction"]
        )
        for entry in qs:
            writer.writerow(
                [
                    entry.date.strftime("%Y-%m-%d %H:%M"),
                    entry.supplier.name,
                    entry.product.name,
                    entry.quantity,
                    entry.value,
                    f"PO{entry.transaction_id:05d}",
                ]
            )
        return response
