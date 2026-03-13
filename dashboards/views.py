from datetime import date, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from django.views.generic import TemplateView

from main.mixins import HtmxPartialMixin
from procurement.models import PurchaseOrder
from sales.models import SalesOrder


class DashboardHomeView(LoginRequiredMixin, TemplateView):
    template_name = "dashboards/home.html"


@method_decorator(cache_page(60 * 5), name="dispatch")
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

        # orders due on this date (exclude closed orders)
        context["orders"] = (
            SalesOrder.objects.filter(
                ship_by_date=current,
                sales_order_lines__complete=False,
            )
            .select_related("customer")
            .prefetch_related("sales_order_lines__product__product", "pick_lists")
            .distinct()
        )

        # week overview
        week_start = context["week_start"]
        week_dates = [week_start + timedelta(days=i) for i in range(7)]
        week_data = []
        for d in week_dates:
            count = (
                SalesOrder.objects.filter(
                    ship_by_date=d,
                    sales_order_lines__complete=False,
                )
                .distinct()
                .count()
            )
            week_data.append(
                {
                    "date": d,
                    "count": count,
                    "is_today": d == today,
                    "is_current": d == current,
                }
            )
        context["week_data"] = week_data

        # overdue orders
        context["overdue_orders"] = (
            SalesOrder.objects.filter(
                ship_by_date__lt=today,
                sales_order_lines__complete=False,
            )
            .select_related("customer")
            .prefetch_related("pick_lists")
            .distinct()
        )

        return context


@method_decorator(cache_page(60 * 5), name="dispatch")
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

        # orders due on this date
        context["orders"] = (
            PurchaseOrder.objects.filter(due_date=current)
            .select_related("supplier")
            .prefetch_related("purchase_order_lines__product__product")
        )

        # week overview
        week_start = context["week_start"]
        week_dates = [week_start + timedelta(days=i) for i in range(7)]
        week_data = []
        for d in week_dates:
            count = PurchaseOrder.objects.filter(due_date=d).count()
            week_data.append(
                {
                    "date": d,
                    "count": count,
                    "is_today": d == today,
                    "is_current": d == current,
                }
            )
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
