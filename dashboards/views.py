from datetime import date, timedelta

from django.views.generic import TemplateView

from procurement.models import PurchaseOrder
from sales.models import SalesOrder


class DashboardHomeView(TemplateView):
    template_name = "dashboards/home.html"


class ShippingScheduleView(TemplateView):
    """Day-based shipping schedule driven by SalesOrder.ship_by_date."""

    template_name = "dashboards/shipping_schedule.html"

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
            SalesOrder.objects.filter(ship_by_date=current)
            .select_related("customer")
            .prefetch_related("sales_order_lines__product__product", "pick_lists")
        )

        # week overview
        week_start = context["week_start"]
        week_dates = [week_start + timedelta(days=i) for i in range(7)]
        week_data = []
        for d in week_dates:
            count = SalesOrder.objects.filter(ship_by_date=d).count()
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


class DeliveryScheduleView(TemplateView):
    """Day-based delivery schedule driven by PurchaseOrder.due_date."""

    template_name = "dashboards/delivery_schedule.html"

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
