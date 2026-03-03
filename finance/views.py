from decimal import Decimal
from typing import Dict, Any

from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.generic import TemplateView
from django.views.generic.dates import ArchiveIndexView, MonthArchiveView

from procurement.models import PurchaseLedger, Supplier
from sales.models import Customer, SalesLedger


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
        return qs

    def _sales_context(self, context: dict) -> dict:
        context["ledger_label"] = "Sales Ledger"
        context["customers"] = Customer.objects.order_by("name")
        context["selected_customer"] = self.request.GET.get("customer", "")
        return context


class SalesLedgerArchiveView(SalesLedgerFilterMixin, LedgerArchiveMixin, ArchiveIndexView):
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
        return context


class SalesLedgerMonthArchiveView(SalesLedgerFilterMixin, LedgerArchiveMixin, MonthArchiveView):
    model = SalesLedger
    template_name = "finance/salesledger_month.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        self._sales_context(context)
        # self.object_list is the month-filtered queryset before pagination
        context["month_total"] = self.object_list.aggregate(
            total=Coalesce(Sum("value"), Decimal("0"))
        )["total"] or Decimal("0")
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


class PurchaseLedgerArchiveView(PurchaseLedgerFilterMixin, LedgerArchiveMixin, ArchiveIndexView):
    model = PurchaseLedger
    template_name = "finance/purchaseledger_archive.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        self._purchase_context(context)
        qs = self.get_queryset()
        context["overall_total"] = qs.aggregate(
            total=Coalesce(Sum("value"), Decimal("0"))
        )["total"] or Decimal("0")
        return context


class PurchaseLedgerMonthArchiveView(PurchaseLedgerFilterMixin, LedgerArchiveMixin, MonthArchiveView):
    model = PurchaseLedger
    template_name = "finance/purchaseledger_month.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        self._purchase_context(context)
        # self.object_list is the month-filtered queryset before pagination
        context["month_total"] = self.object_list.aggregate(
            total=Coalesce(Sum("value"), Decimal("0"))
        )["total"] or Decimal("0")
        return context
