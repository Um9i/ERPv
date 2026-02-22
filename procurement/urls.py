from django.urls import path
from django.views.generic import TemplateView
from .views import (
    SupplierCreateView,
    SupplierUpdateView,
    SupplierDeleteView,
    SupplierListView,
    SupplierDetailView,
    SupplierContactCreateView,
    SupplierContactUpdateView,
    SupplierContactDeleteView,
    SupplierProductCreateView,
    SupplierPurchaseOrderListView,
    SupplierProductListView,
    SupplierProductIDsView,
    SupplierProductUpdateView,
    SupplierProductDeleteView,
    PurchaseOrderCreateView,
    PurchaseOrderDetailView,
    PurchaseOrderReceivingListView,
    PurchaseOrderReceiveView,
    PurchaseOrderListView,
    ProcurementDashboardView,
)

app_name = "procurement"

urlpatterns = [
    path("", ProcurementDashboardView.as_view(), name="procurement-dashboard"),
    path("suppliers/", SupplierListView.as_view(), name="supplier-list"),
    path("suppliers/<int:pk>/", SupplierDetailView.as_view(), name="supplier-detail"),
    path("suppliers/create/", SupplierCreateView.as_view(), name="supplier-create"),
    path("suppliers/<int:pk>/update/", SupplierUpdateView.as_view(), name="supplier-update"),
    path("suppliers/<int:pk>/delete/", SupplierDeleteView.as_view(), name="supplier-delete"),
    path("supplier-contacts/create/", SupplierContactCreateView.as_view(), name="supplier-contact-create"),
    path("supplier-contacts/<int:pk>/update/", SupplierContactUpdateView.as_view(), name="supplier-contact-update"),
    path("supplier-contacts/<int:pk>/delete/", SupplierContactDeleteView.as_view(), name="supplier-contact-delete"),
    path("supplier-products/create/", SupplierProductCreateView.as_view(), name="supplier-product-create"),
    path("supplier-products/<int:pk>/update/", SupplierProductUpdateView.as_view(), name="supplier-product-update"),
    path("supplier-products/<int:pk>/delete/", SupplierProductDeleteView.as_view(), name="supplier-product-delete"),
    path("supplier/<int:pk>/purchase-orders/", SupplierPurchaseOrderListView.as_view(), name="supplier-purchaseorders"),
    path("supplier/<int:pk>/products/", SupplierProductListView.as_view(), name="supplier-products"),
    path("supplier/<int:pk>/product-ids/", SupplierProductIDsView.as_view(), name="supplier-product-ids"),
    path("purchase-orders/", PurchaseOrderListView.as_view(), name="purchase-order-list"),
    path("purchase-orders/create/", PurchaseOrderCreateView.as_view(), name="purchase-order-create"),
    path("purchase-orders/<int:pk>/", PurchaseOrderDetailView.as_view(), name="purchase-order-detail"),
    path("purchase-orders/receiving/", PurchaseOrderReceivingListView.as_view(), name="purchase-order-receiving-list"),
    path("purchase-orders/<int:pk>/receive/", PurchaseOrderReceiveView.as_view(), name="purchase-order-receive"),
]
