from django.contrib import admin
from django_admin_inline_paginator.admin import TabularInlinePaginated

from inventory.admin import ExportCsvMixin

from .models import (
    PurchaseLedger,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierContact,
    SupplierProduct,
)


class PurchaseLedgerInline(TabularInlinePaginated):
    model = PurchaseLedger
    extra = 0
    readonly_fields = [
        "product",
        "quantity",
        "supplier",
        "transaction_id",
        "value",
        "date",
    ]
    per_page = 15


@admin.register(PurchaseLedger)
class PurchaseLedgerAdmin(admin.ModelAdmin, ExportCsvMixin):
    list_display = [
        "product",
        "quantity",
        "supplier",
        "transaction_id",
        "value",
        "date",
    ]
    list_filter = ["date", "supplier", "product"]
    list_select_related = ["product", "supplier"]
    list_per_page = 50
    search_fields = ["product__name", "supplier__name"]
    actions = ["export_as_csv"]
    readonly_fields = [
        "product",
        "quantity",
        "supplier",
        "transaction_id",
        "value",
        "date",
    ]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions


@admin.register(SupplierProduct)
class SupplierProductAdmin(admin.ModelAdmin):
    autocomplete_fields = ["supplier", "product"]
    list_display = ["product", "supplier", "cost"]
    list_filter = ["supplier"]
    list_select_related = ["product", "supplier"]
    search_fields = ["product"]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

    def get_model_perms(self, request):
        return {}


class SupplierContactInline(admin.StackedInline):
    model = SupplierContact
    extra = 0


class SupplierProductInline(TabularInlinePaginated):
    model = SupplierProduct
    extra = 0
    autocomplete_fields = ["product"]
    readonly_fields = ["on_purchase_order"]
    per_page = 15


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 0
    autocomplete_fields = ["product"]
    readonly_fields = ["closed", "value"]

    def value(self, obj):
        return obj.product.cost * obj.quantity


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    inlines = [
        SupplierContactInline,
        SupplierProductInline,
    ]
    list_display = ["name"]
    list_per_page = 15
    search_fields = ["name"]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    autocomplete_fields = ["supplier"]
    inlines = [
        PurchaseOrderLineInline,
    ]
    list_display = ["id", "supplier"]
    list_filter = ["supplier"]
    list_select_related = ["supplier"]
    search_fields = ["id"]
    actions = ["mark_lines_complete", "close_selected_orders"]

    @admin.action(description="Mark all lines as complete")
    def mark_lines_complete(self, request, queryset):
        count = 0
        for po in queryset:
            updated = po.purchase_order_lines.filter(complete=False).update(
                complete=True, closed=True
            )
            count += updated
        self.message_user(request, f"{count} line(s) marked complete.")

    @admin.action(description="Close selected orders")
    def close_selected_orders(self, request, queryset):
        count = 0
        for po in queryset:
            po.purchase_order_lines.filter(closed=False).update(
                closed=True, complete=True
            )
            count += 1
        self.message_user(request, f"{count} order(s) closed.")

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions
