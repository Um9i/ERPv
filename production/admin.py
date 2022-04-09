from django.contrib import admin
from .models import BillOfMaterials, BOMItem, Production


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
    list_per_page = 15
    search_fields = ["product"]
    readonly_fields = ["closed", "bom_allocated", "bom_allocated_amount"]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions
