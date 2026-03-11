from django.contrib import admin

from inventory.admin import ExportCsvMixin

from .models import BillOfMaterials, BOMItem, Production, ProductionLedger


class BOMItemInline(admin.TabularInline):
    autocomplete_fields = ["product"]
    model = BOMItem
    extra = 0


@admin.register(BillOfMaterials)
class BillOfMaterialsAdmin(admin.ModelAdmin):
    autocomplete_fields = ["product"]
    inlines = [
        BOMItemInline,
    ]
    list_display = ["product"]
    list_per_page = 15
    search_fields = ["product"]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions


@admin.register(Production)
class ProductionAdmin(admin.ModelAdmin):
    autocomplete_fields = ["product"]
    list_display = ["id", "product", "quantity", "complete"]
    list_filter = ["complete"]
    list_select_related = ["product"]
    list_per_page = 15
    search_fields = ["product"]
    readonly_fields = ["closed", "bom_allocated", "bom_allocated_amount"]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions


@admin.register(ProductionLedger)
class ProductionLedgerAdmin(admin.ModelAdmin, ExportCsvMixin):
    list_display = ["product", "quantity", "transaction_id", "value", "date"]
    list_filter = ["date", "product"]
    list_select_related = ["product"]
    list_per_page = 50
    search_fields = ["product__name"]
    actions = ["export_as_csv"]
    readonly_fields = ["product", "quantity", "transaction_id", "value", "date"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions
