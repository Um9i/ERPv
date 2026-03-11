from django.contrib import admin

from .models import FinanceDashboardSnapshot


@admin.register(FinanceDashboardSnapshot)
class FinanceDashboardSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "pk",
        "sales_total",
        "purchase_total",
        "month_sales_total",
        "month_purchase_total",
        "stock_value",
        "updated_at",
    ]
    readonly_fields = [
        "sales_total",
        "purchase_total",
        "month_sales_total",
        "month_purchase_total",
        "month_year",
        "month_month",
        "stock_value",
        "chart_data_json",
        "updated_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
