from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Dict, Any

from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.generic import TemplateView
from django.views.generic.dates import ArchiveIndexView, MonthArchiveView

from procurement.models import PurchaseLedger
from sales.models import SalesLedger

try:
    from weasyprint import HTML
except ImportError:  # pragma: no cover - optional dependency
    HTML = None


class FinanceDashboardView(TemplateView):
    template_name = "finance/dashboard.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        sales_total = SalesLedger.objects.aggregate(total=Coalesce(Sum("value"), Decimal("0")))
        purchase_total = PurchaseLedger.objects.aggregate(total=Coalesce(Sum("value"), Decimal("0")))

        now = timezone.now()
        month_filter = {"date__year": now.year, "date__month": now.month}
        month_sales = SalesLedger.objects.filter(**month_filter).aggregate(
            total=Coalesce(Sum("value"), Decimal("0"))
        )
        month_purchases = PurchaseLedger.objects.filter(**month_filter).aggregate(
            total=Coalesce(Sum("value"), Decimal("0"))
        )

        context.update(
            {
                "now": now,
                "sales_total": sales_total.get("total") or Decimal("0"),
                "purchase_total": purchase_total.get("total") or Decimal("0"),
                "month_sales_total": month_sales.get("total") or Decimal("0"),
                "month_purchase_total": month_purchases.get("total") or Decimal("0"),
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


class InvoiceMonthMixin:
    date_field = "date"
    allow_empty = True
    allow_future = False
    month_format = "%m"
    make_object_list = True

    def _period_bounds(self) -> Dict[str, date]:
        year = int(self.get_year())
        month = int(self.get_month())
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        return {"period_start": start, "period_end": end}


class CustomerInvoiceMonthView(InvoiceMonthMixin, MonthArchiveView):
    model = SalesLedger
    template_name = "finance/customer_invoice_month.html"

    def get_queryset(self):
        return super().get_queryset().select_related("customer", "product")

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        bounds = self._period_bounds()
        invoices = (
            self.get_queryset()
            .filter(date__year=bounds["period_start"].year, date__month=bounds["period_start"].month)
            .values("customer__id", "customer__name")
            .annotate(
                total_quantity=Coalesce(Sum("quantity"), 0),
                total_value=Coalesce(Sum("value"), Decimal("0")),
            )
            .order_by("customer__name")
        )
        ledger_rows = (
            self.get_queryset()
            .filter(date__year=bounds["period_start"].year, date__month=bounds["period_start"].month)
            .order_by("customer__name", "date")
        )
        context.update(
            {
                "period_start": bounds["period_start"],
                "period_end": bounds["period_end"],
                "invoice_rows": invoices,
                "ledger_rows": ledger_rows,
                "ledger_label": "Customer Invoices",
            }
        )
        return context


class PdfResponseMixin:
    pdf_filename_prefix = "finance"

    def get_pdf_filename(self) -> str:
        year = self.kwargs.get("year")
        month = self.kwargs.get("month")
        return f"{self.pdf_filename_prefix}-{year}-{month}.pdf"

    def render_to_response(self, context: Dict[str, Any], **response_kwargs: Any):
        if HTML is None:
            return HttpResponse(
                "PDF generation requires WeasyPrint. Install it with `pip install weasyprint`.",
                status=501,
            )
        html = render_to_string(self.template_name, context, request=self.request)
        pdf_bytes = HTML(string=html, base_url=self.request.build_absolute_uri()).write_pdf()
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f"attachment; filename={self.get_pdf_filename()}"
        return response


class CustomerInvoiceMonthPdfView(PdfResponseMixin, CustomerInvoiceMonthView):
    template_name = "finance/customer_invoice_month_pdf.html"
    pdf_filename_prefix = "customer-invoices"


class SupplierBillingMonthView(InvoiceMonthMixin, MonthArchiveView):
    model = PurchaseLedger
    template_name = "finance/supplier_billing_month.html"

    def get_queryset(self):
        return super().get_queryset().select_related("supplier", "product")

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        bounds = self._period_bounds()
        supplier_rows = (
            self.get_queryset()
            .filter(date__year=bounds["period_start"].year, date__month=bounds["period_start"].month)
            .values("supplier__id", "supplier__name")
            .annotate(
                total_quantity=Coalesce(Sum("quantity"), 0),
                total_value=Coalesce(Sum("value"), Decimal("0")),
            )
            .order_by("supplier__name")
        )
        ledger_rows = (
            self.get_queryset()
            .filter(date__year=bounds["period_start"].year, date__month=bounds["period_start"].month)
            .order_by("supplier__name", "date")
        )
        context.update(
            {
                "period_start": bounds["period_start"],
                "period_end": bounds["period_end"],
                "supplier_rows": supplier_rows,
                "ledger_rows": ledger_rows,
                "ledger_label": "Supplier Bills",
            }
        )
        return context
