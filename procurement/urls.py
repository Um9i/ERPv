from django.urls import path
from .views import (
    SupplierCreateView,
    SupplierUpdateView,
    SupplierDeleteView,
    SupplierListView,
    SupplierDetailView,
    SupplierContactCreateView,
    SupplierProductCreateView,
    PurchaseOrderCreateView,
)

app_name = "procurement"

urlpatterns = [
    path("suppliers/", SupplierListView.as_view(), name="supplier-list"),
    path("suppliers/<int:pk>/", SupplierDetailView.as_view(), name="supplier-detail"),
    path("suppliers/create/", SupplierCreateView.as_view(), name="supplier-create"),
    path("suppliers/<int:pk>/update/", SupplierUpdateView.as_view(), name="supplier-update"),
    path("suppliers/<int:pk>/delete/", SupplierDeleteView.as_view(), name="supplier-delete"),
    path("supplier-contacts/create/", SupplierContactCreateView.as_view(), name="supplier-contact-create"),
    path("supplier-products/create/", SupplierProductCreateView.as_view(), name="supplier-product-create"),
    path("purchase-orders/create/", PurchaseOrderCreateView.as_view(), name="purchase-order-create"),
]
