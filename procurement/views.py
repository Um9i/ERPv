from .models import Supplier, SupplierContact, SupplierProduct, PurchaseOrder
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
)
from django.urls import reverse_lazy


class SupplierCreateView(CreateView):
    model = Supplier
    template_name = "procurement/supplier_form.html"
    fields = ["name", "address", "phone", "email", "website"]
    success_url = reverse_lazy("procurement:supplier-list")


class SupplierUpdateView(UpdateView):
    model = Supplier
    template_name = "procurement/supplier_form.html"
    fields = ["name", "address", "phone", "email", "website"]
    success_url = reverse_lazy("procurement:supplier-list")


class SupplierDeleteView(DeleteView):
    model = Supplier
    template_name = "procurement/supplier_confirm_delete.html"
    success_url = reverse_lazy("procurement:supplier-list")


class SupplierListView(ListView):
    model = Supplier
    template_name = "procurement/supplier_list.html"
    context_object_name = "suppliers"


class SupplierDetailView(DetailView):
    model = Supplier
    template_name = "procurement/supplier_detail.html"
    context_object_name = "supplier"

    def get_context_data(self, **kwargs):
        # include related objects so the template can render tables without
        # additional queries in the template itself.
        context = super().get_context_data(**kwargs)
        supplier = self.object
        context["purchase_orders"] = supplier.supplier_purchase_orders.all()
        context["supplier_products"] = supplier.supplier_products.all()
        return context


class SupplierContactCreateView(CreateView):
    model = SupplierContact
    template_name = "procurement/supplier_contact_form.html"
    fields = ["supplier", "name", "email", "phone"]
    success_url = reverse_lazy("procurement:supplier-list")


class SupplierProductCreateView(CreateView):
    model = SupplierProduct
    template_name = "procurement/supplier_product_form.html"
    fields = ["supplier", "product", "cost"]
    success_url = reverse_lazy("procurement:supplier-list")


class PurchaseOrderCreateView(CreateView):
    model = PurchaseOrder
    template_name = "procurement/purchase_order_form.html"
    fields = ["supplier"]
    success_url = reverse_lazy("procurement:supplier-list")

