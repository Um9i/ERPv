"""Main app views."""

import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connection
from django.db.models import Q
from django.http import JsonResponse
from django.views import View
from django.views.generic import TemplateView

logger = logging.getLogger(__name__)


class HealthCheckView(View):
    """Unauthenticated health-check endpoint for container orchestration."""

    def get(self, request):
        status: dict[str, object] = {"status": "ok"}
        checks: dict[str, str] = {}

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "error"
            status["status"] = "error"
            logger.exception("Health check: database unreachable")

        status["checks"] = checks
        code = 200 if status["status"] == "ok" else 503
        return JsonResponse(status, status=code)


class GlobalSearchView(LoginRequiredMixin, TemplateView):
    template_name = "search_results.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        q = self.request.GET.get("q", "").strip()
        context["q"] = q
        if not q:
            return context

        from inventory.models import Inventory
        from procurement.models import PurchaseOrder, Supplier
        from production.models import BillOfMaterials, Production
        from sales.models import Customer, SalesOrder

        context["products"] = Inventory.objects.filter(
            product__name__icontains=q
        ).select_related("product")[:10]
        context["suppliers"] = Supplier.objects.filter(
            Q(name__icontains=q) | Q(email__icontains=q)
        )[:10]
        context["customers"] = Customer.objects.filter(
            Q(name__icontains=q) | Q(email__icontains=q)
        )[:10]
        context["purchase_orders"] = (
            PurchaseOrder.objects.filter(
                Q(supplier__name__icontains=q) | Q(pk__icontains=q)
            )
            .select_related("supplier")
            .order_by("-created_at")[:10]
        )
        context["sales_orders"] = (
            SalesOrder.objects.filter(
                Q(customer__name__icontains=q) | Q(pk__icontains=q)
            )
            .select_related("customer")
            .order_by("-created_at")[:10]
        )
        context["production_jobs"] = (
            Production.objects.filter(
                Q(product__name__icontains=q) | Q(pk__icontains=q)
            )
            .select_related("product")
            .order_by("-created_at")[:10]
        )
        context["boms"] = BillOfMaterials.objects.filter(
            product__name__icontains=q
        ).select_related("product")[:10]
        context["has_results"] = any(
            context[k]
            for k in (
                "products",
                "suppliers",
                "customers",
                "purchase_orders",
                "sales_orders",
                "production_jobs",
                "boms",
            )
        )
        return context
