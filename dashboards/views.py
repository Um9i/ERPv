from datetime import date, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Exists, F, OuterRef, Subquery, Sum
from django.db.models.functions import Greatest
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from django.views.generic import TemplateView

from main.mixins import HtmxPartialMixin
from procurement.models import PurchaseOrder
from production.models import Production
from sales.models import SalesOrder


class DashboardHomeView(LoginRequiredMixin, TemplateView):
    template_name = "dashboards/home.html"


@method_decorator(vary_on_headers("HX-Request"), name="dispatch")
class ShippingScheduleView(HtmxPartialMixin, LoginRequiredMixin, TemplateView):
    """Day-based shipping schedule driven by SalesOrder.ship_by_date."""

    template_name = "dashboards/shipping_schedule.html"
    partial_template_name = "dashboards/_shipping_metrics.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        raw = self.request.GET.get("date")
        if raw:
            try:
                current = date.fromisoformat(raw)
            except ValueError:
                current = today
        else:
            current = today

        context["current_date"] = current
        context["today"] = today
        context["prev_date"] = current - timedelta(days=1)
        context["next_date"] = current + timedelta(days=1)
        context["week_start"] = current - timedelta(days=current.weekday())

        # Subquery annotations so status / remaining_total don't fire per-row
        from sales.models import SalesOrderLine

        _open_lines_exists = Exists(
            SalesOrderLine.objects.filter(
                sales_order=OuterRef("pk"),
                complete=False,
            ).exclude(quantity_shipped__gte=F("quantity"))
        )
        _remaining_sub = Subquery(
            SalesOrderLine.objects.filter(sales_order=OuterRef("pk"))
            .values("sales_order")
            .annotate(
                val=Sum(
                    F("product__price")
                    * Greatest(F("quantity") - F("quantity_shipped"), 0)
                )
            )
            .values("val")[:1]
        )

        # orders due on this date (exclude closed orders)
        context["orders"] = (
            SalesOrder.objects.filter(
                ship_by_date=current,
                sales_order_lines__complete=False,
            )
            .select_related("customer")
            .prefetch_related("pick_lists")
            .annotate(
                _has_open_lines=_open_lines_exists,
                _remaining_total=_remaining_sub,
            )
            .distinct()
        )

        # week overview – single query instead of 7 individual counts
        week_start = context["week_start"]
        week_dates = [week_start + timedelta(days=i) for i in range(7)]
        counts_qs = (
            SalesOrder.objects.filter(
                ship_by_date__in=week_dates,
                sales_order_lines__complete=False,
            )
            .values("ship_by_date")
            .annotate(cnt=Count("id", distinct=True))
        )
        counts_by_date = {row["ship_by_date"]: row["cnt"] for row in counts_qs}
        week_data = [
            {
                "date": d,
                "count": counts_by_date.get(d, 0),
                "is_today": d == today,
                "is_current": d == current,
            }
            for d in week_dates
        ]
        context["week_data"] = week_data

        # overdue orders
        context["overdue_orders"] = (
            SalesOrder.objects.filter(
                ship_by_date__lt=today,
                sales_order_lines__complete=False,
            )
            .select_related("customer")
            .prefetch_related("pick_lists")
            .annotate(
                _has_open_lines=_open_lines_exists,
                _remaining_total=_remaining_sub,
            )
            .distinct()
        )

        return context


@method_decorator(vary_on_headers("HX-Request"), name="dispatch")
class DeliveryScheduleView(HtmxPartialMixin, LoginRequiredMixin, TemplateView):
    """Day-based delivery schedule driven by PurchaseOrder.due_date."""

    template_name = "dashboards/delivery_schedule.html"
    partial_template_name = "dashboards/_delivery_metrics.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        raw = self.request.GET.get("date")
        if raw:
            try:
                current = date.fromisoformat(raw)
            except ValueError:
                current = today
        else:
            current = today

        context["current_date"] = current
        context["today"] = today
        context["prev_date"] = current - timedelta(days=1)
        context["next_date"] = current + timedelta(days=1)
        context["week_start"] = current - timedelta(days=current.weekday())

        # orders due on this date (exclude closed orders)
        context["orders"] = (
            PurchaseOrder.objects.filter(
                due_date=current,
                purchase_order_lines__complete=False,
            )
            .select_related("supplier")
            .prefetch_related("purchase_order_lines__product__product")
            .distinct()
        )

        # week overview – single query instead of 7 individual counts
        week_start = context["week_start"]
        week_dates = [week_start + timedelta(days=i) for i in range(7)]
        counts_qs = (
            PurchaseOrder.objects.filter(
                due_date__in=week_dates,
                purchase_order_lines__complete=False,
            )
            .values("due_date")
            .annotate(cnt=Count("id", distinct=True))
        )
        counts_by_date = {row["due_date"]: row["cnt"] for row in counts_qs}
        week_data = [
            {
                "date": d,
                "count": counts_by_date.get(d, 0),
                "is_today": d == today,
                "is_current": d == current,
            }
            for d in week_dates
        ]
        context["week_data"] = week_data

        # overdue orders
        context["overdue_orders"] = (
            PurchaseOrder.objects.filter(
                due_date__lt=today,
                purchase_order_lines__complete=False,
            )
            .select_related("supplier")
            .distinct()
        )

        return context


@method_decorator(vary_on_headers("HX-Request"), name="dispatch")
class ProductionScheduleView(HtmxPartialMixin, LoginRequiredMixin, TemplateView):
    """Day-based production schedule driven by Production.due_date."""

    template_name = "dashboards/production_schedule.html"
    partial_template_name = "dashboards/_production_metrics.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        raw = self.request.GET.get("date")
        if raw:
            try:
                current = date.fromisoformat(raw)
            except ValueError:
                current = today
        else:
            current = today

        context["current_date"] = current
        context["today"] = today
        context["prev_date"] = current - timedelta(days=1)
        context["next_date"] = current + timedelta(days=1)
        context["week_start"] = current - timedelta(days=current.weekday())

        # production jobs due on this date (exclude closed jobs)
        context["jobs"] = Production.objects.filter(
            due_date=current,
            closed=False,
        ).select_related("product")

        # week overview – single query instead of 7 individual counts
        week_start = context["week_start"]
        week_dates = [week_start + timedelta(days=i) for i in range(7)]
        counts_qs = (
            Production.objects.filter(
                due_date__in=week_dates,
                closed=False,
            )
            .values("due_date")
            .annotate(cnt=Count("id"))
        )
        counts_by_date = {row["due_date"]: row["cnt"] for row in counts_qs}
        week_data = [
            {
                "date": d,
                "count": counts_by_date.get(d, 0),
                "is_today": d == today,
                "is_current": d == current,
            }
            for d in week_dates
        ]
        context["week_data"] = week_data

        # overdue jobs
        context["overdue_jobs"] = Production.objects.filter(
            due_date__lt=today,
            closed=False,
        ).select_related("product")

        return context
