import csv
from django.http import HttpResponse
from django.contrib import admin
from .models import Product, Inventory, InventoryLedger, InventoryAdjust
from django_admin_inline_paginator.admin import TabularInlinePaginated


class ExportCsvMixin:
    def export_as_csv(self, request, queryset):

        meta = self.model._meta
        field_names = [field.name for field in meta.fields]

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename={}.csv".format(meta)
        writer = csv.writer(response)

        writer.writerow(field_names)
        for obj in queryset:
            row = writer.writerow([getattr(obj, field) for field in field_names])

        return response

    export_as_csv.short_description = "Export Selected"


@admin.register(InventoryLedger)
class InventoryLedgerAdmin(admin.ModelAdmin, ExportCsvMixin):
    list_display = ["product", "quantity", "action", "transaction_id", "date"]
    list_filter = ["action", "date"]
    list_per_page = 50
    search_fields = ["product__name", "transaction_id"]
    actions = ["export_as_csv"]
    readonly_fields = ["product", "quantity", "action", "transaction_id", "date"]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions


class InventoryLedgerInline(TabularInlinePaginated):
    model = InventoryLedger
    extra = 0
    readonly_fields = ["quantity", "action", "transaction_id", "date"]
    per_page = 15


class InventoryInline(admin.TabularInline):
    model = Inventory
    extra = 0
    autocomplete_fields = ["product"]


class InventoryAdjustInline(TabularInlinePaginated):
    model = InventoryAdjust
    extra = 0
    autocomplete_fields = ["product"]
    readonly_fields = ["closed"]
    per_page = 5


@admin.register(InventoryAdjust)
class InventoryAdjustAdmin(admin.ModelAdmin):
    autocomplete_fields = ["product"]
    readonly_fields = ["closed"]
    list_display = ["product", "quantity"]
    search_fields = ["product"]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = [
        InventoryLedgerInline,
    ]
    list_display = ["name", "inventory_quantity", "required"]
    list_per_page = 15
    search_fields = ["name"]
    fields = (
        ("name"),
        ("inventory_quantity", "planned_production", "production_allocated"),
        ("on_sales_order", "on_purchase_order", "required"),
    )
    readonly_fields = [
        "inventory_quantity",
        "planned_production",
        "on_sales_order",
        "on_purchase_order",
        "production_allocated",
        "required",
    ]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

    def inventory_quantity(self, obj) -> int:
        return obj.product_inventory.quantity

    def planned_production(self, obj) -> int:
        try:
            jobs = sum(
                [job.quantity for job in obj.product_jobs.filter(complete=False)]
            )
            return jobs
        except:
            pass

    def production_allocated(self, obj) -> int:
        try:
            allocated = sum([job.quantity for job in obj.production_allocated.all()])
            return allocated
        except:
            pass

    def on_sales_order(self, obj) -> int:
        try:
            orders = sum(
                [
                    sold_product.on_sales_order()
                    for sold_product in obj.product_customers.all()
                ]
            )
            return orders
        except:
            pass

    def on_purchase_order(self, obj) -> int:
        try:
            orders = sum(
                [
                    purchased_product.on_purchase_order()
                    for purchased_product in obj.product_suppliers.all()
                ]
            )
            return orders
        except:
            pass

    def required(self, obj) -> int:
        allocated = sum([job.quantity for job in obj.production_allocated.all()])
        purchase_orders = sum(
            [
                purchased_product.on_purchase_order()
                for purchased_product in obj.product_suppliers.all()
            ]
        )
        sales_orders = sum(
            [
                sold_product.on_sales_order()
                for sold_product in obj.product_customers.all()
            ]
        )
        planned = sum([job.quantity for job in obj.product_jobs.filter(complete=False)])
        required = obj.product_inventory.quantity - allocated - sales_orders
        if required < 0:
            return abs(required)
        else:
            return 0

    inventory_quantity.admin_order_field = "product_inventory__quantity"
    required.admin_order_field = "product_inventory__required"
