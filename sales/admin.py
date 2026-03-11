from django.contrib import admin
from django_admin_inline_paginator.admin import TabularInlinePaginated

from inventory.admin import ExportCsvMixin

from .models import (
    Customer,
    CustomerContact,
    CustomerProduct,
    SalesLedger,
    SalesOrder,
    SalesOrderLine,
)


class SalesLedgerInline(TabularInlinePaginated):
    model = SalesLedger
    extra = 0
    readonly_fields = [
        "product",
        "quantity",
        "customer",
        "transaction_id",
        "value",
        "date",
    ]
    per_page = 15


@admin.register(SalesLedger)
class SalesLedgerAdmin(admin.ModelAdmin, ExportCsvMixin):
    list_display = [
        "product",
        "quantity",
        "customer",
        "transaction_id",
        "value",
        "date",
    ]
    list_filter = ["date", "customer", "product"]
    list_select_related = ["product", "customer"]
    list_per_page = 50
    search_fields = ["product__name", "customer__name"]
    actions = ["export_as_csv"]
    readonly_fields = [
        "product",
        "quantity",
        "customer",
        "transaction_id",
        "value",
        "date",
    ]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions


@admin.register(CustomerProduct)
class CustomerProductAdmin(admin.ModelAdmin):
    autocomplete_fields = ["customer", "product"]
    list_display = ["product", "customer", "price"]
    list_filter = ["customer"]
    list_select_related = ["product", "customer"]
    search_fields = ["product"]

    def get_model_perms(self, request):
        return {}

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions


class CustomerContactInline(admin.StackedInline):
    model = CustomerContact
    extra = 0


class CustomerProductInline(admin.TabularInline):
    model = CustomerProduct
    extra = 0
    autocomplete_fields = ["product"]
    readonly_fields = ["on_sales_order"]


class SalesOrderLineInline(admin.TabularInline):
    model = SalesOrderLine
    extra = 0
    autocomplete_fields = ["product"]
    readonly_fields = ["closed", "value", "quantity_shipped"]


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    inlines = [
        CustomerContactInline,
        CustomerProductInline,
    ]
    list_display = ["name"]
    list_per_page = 15
    search_fields = ["name"]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    autocomplete_fields = ["customer"]
    inlines = [
        SalesOrderLineInline,
    ]
    list_display = ["id", "customer"]
    list_filter = ["customer"]
    list_select_related = ["customer"]
    search_fields = ["id"]
    actions = ["mark_lines_complete", "close_selected_orders"]

    @admin.action(description="Mark all lines as complete")
    def mark_lines_complete(self, request, queryset):
        count = 0
        for so in queryset:
            updated = so.sales_order_lines.filter(complete=False).update(
                complete=True, closed=True
            )
            count += updated
        self.message_user(request, f"{count} line(s) marked complete.")

    @admin.action(description="Close selected orders")
    def close_selected_orders(self, request, queryset):
        count = 0
        for so in queryset:
            so.sales_order_lines.filter(closed=False).update(closed=True, complete=True)
            count += 1
        self.message_user(request, f"{count} order(s) closed.")

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions
