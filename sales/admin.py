from django.contrib import admin
from .models import (
    Customer,
    CustomerContact,
    CustomerProduct,
    SalesOrder,
    SalesOrderLine,
    SalesLedger,
)
from django_admin_inline_paginator.admin import TabularInlinePaginated
from inventory.admin import ExportCsvMixin


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
    list_filter = ["date"]
    list_per_page = 50
    search_fields = ["product__name", "customer"]
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
    readonly_fields = ["closed", "value"]


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
    search_fields = ["id"]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions
