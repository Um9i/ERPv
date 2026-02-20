from django.shortcuts import render
from .models import Product, Inventory, InventoryAdjust
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
)
from django.urls import reverse_lazy


class ProductCreateView(CreateView):
    model = Product
    template_name = "inventory/product_form.html"
    fields = ["name"]
    success_url = reverse_lazy("inventory:inventory-list")


class ProductUpdateView(UpdateView):
    model = Product
    template_name = "inventory/product_form.html"
    fields = ["name"]
    success_url = reverse_lazy("inventory:inventory-list")


class ProductDeleteView(DeleteView):
    model = Product
    template_name = "inventory/product_confirm_delete.html"
    success_url = reverse_lazy("inventory:inventory-list")


class InventoryListView(ListView):
    model = Inventory
    template_name = "inventory/inventory_list.html"
    context_object_name = "inventories"

    def get_queryset(self):
        return Inventory.objects.all().select_related("product")


class InventoryDetailView(DetailView):
    model = Inventory
    template_name = "inventory/inventory_detail.html"
    context_object_name = "inventory"

    def get_queryset(self):
        return Inventory.objects.all().select_related("product")


class InventoryAdjustCreateView(CreateView):
    model = InventoryAdjust
    template_name = "inventory/inventory_adjust_form.html"
    fields = ["product", "quantity"]
    success_url = reverse_lazy("inventory:inventory-list")

    def get_initial(self):
        initial = super().get_initial()
        inventory = Inventory.objects.select_related("product").get(pk=self.kwargs.get("pk"))
        initial["product"] = inventory.product
        return initial

    def get_form(self, *args, **kwargs):
        form = super().get_form(*args, **kwargs)
        form.fields["product"].disabled = True
        if "complete" in form.fields:
            del form.fields["complete"]
        return form

    def form_valid(self, form):
        inventory = Inventory.objects.select_related("product").get(pk=self.kwargs.get("pk"))
        form.instance.product = inventory.product
        form.instance.complete = True
        return super().form_valid(form)
