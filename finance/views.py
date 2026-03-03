from decimal import Decimal
from typing import Dict, Any

from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.generic import TemplateView
from django.views.generic.dates import ArchiveIndexView, MonthArchiveView

from procurement.models import PurchaseLedger
from sales.models import SalesLedger


class FinanceDashboardView(TemplateView):
    template_name = "finance/dashboard.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        sales_total = SalesLedger.objects.aggregate(total=Coalesce(Sum("value"), Decimal("0")))["total"] or Decimal("0")
        purchase_total = PurchaseLedger.objects.aggregate(total=Coalesce(Sum("value"), Decimal("0")))["total"] or Decimal("0")

        now = timezone.now()
        month_filter = {"date__year": now.year, "date__month": now.month}
        month_sales = SalesLedger.objects.filter(**month_filter).aggregate(
            total=Coalesce(Sum("value"), Decimal("0"))
        )["total"] or Decimal("0")
        month_purchases = PurchaseLedger.objects.filter(**month_filter).aggregate(
            total=Coalesce(Sum("value"), Decimal("0"))
        )["total"] or Decimal("0")

        context.update(
            {
                "now": now,
                "sales_total": sales_total,
                "purchase_total": purchase_total,
                "gross_profit": sales_total - purchase_total,
                "month_sales_total": month_sales,
                "month_purchase_total": month_purchases,
                "month_profit": month_sales - month_purchases,
                "recent_sales": SalesLedger.objects.select_related("customer", "product")
                .order_by("-date")[:5],
                "recent_purchases": PurchaseLedger.objects.select_related("supplier", "product")
                .order_by("-date")[:5],
            }
        )
        return context


class LedgerArchiveMixin:
    date_field = "date"
    allow_future = False
    allow_empty = True
    paginate_by = 50
    month_format = "%m"
    make_object_list = True

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.setdefault("ledger_label", "Ledger")
        context.setdefault("today", timezone.now())
        return context


class SalesLedgerArchiveView(LedgerArchiveMixin, ArchiveIndexView):
    model = SalesLedger
    template_name = "finance/salesledger_archive.html"

    def get_queryset(self):
        return super().get_queryset().select_related("customer", "product")

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["ledger_label"] = "Sales Ledger"
        month_total = (
            context.get("object_list")
            .aggregate(total=Coalesce(Sum("value"), Decimal("0")))
            .get("total")
        )
        context["month_total"] = month_total or Decimal("0")
        return context


class SalesLedgerMonthArchiveView(LedgerArchiveMixin, MonthArchiveView):
    model = SalesLedger
    template_name = "finance/salesledger_month.html"

    def get_queryset(self):
        return super().get_queryset().select_related("customer", "product")

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["ledger_label"] = "Sales Ledger"
        return context


class PurchaseLedgerArchiveView(LedgerArchiveMixin, ArchiveIndexView):
    model = PurchaseLedger
    template_name = "finance/purchaseledger_archive.html"

    def get_queryset(self):
        return super().get_queryset().select_related("supplier", "product")

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["ledger_label"] = "Purchase Ledger"
        month_total = (
            context.get("object_list")
            .aggregate(total=Coalesce(Sum("value"), Decimal("0")))
            .get("total")
        )
        context["month_total"] = month_total or Decimal("0")
        return context


class PurchaseLedgerMonthArchiveView(LedgerArchiveMixin, MonthArchiveView):
    model = PurchaseLedger
    template_name = "finance/purchaseledger_month.html"

    def get_queryset(self):
        return super().get_queryset().select_related("supplier", "product")

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["ledger_label"] = "Purchase Ledger"
        return context
