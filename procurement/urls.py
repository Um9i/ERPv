from django.urls import path
from django.views.generic import TemplateView
from .views import (
    SupplierCreateView,
    SupplierUpdateView,
    SupplierDeleteView,
    SupplierListView,
    SupplierDetailView,
    SupplierContactCreateView,
    SupplierProductCreateView,
    PurchaseOrderCreateView,
    PurchaseOrderDetailView,
    SupplierPurchaseOrderListView,
    SupplierProductListView,
    PurchaseOrderReceivingListView,
    PurchaseOrderReceiveView,
)

app_name = "procurement"

urlpatterns = [
    path("", TemplateView.as_view(template_name="procurement/procurement_dashboard.html"), name="procurement-dashboard"),
    path("suppliers/", SupplierListView.as_view(), name="supplier-list"),
    path("suppliers/<int:pk>/", SupplierDetailView.as_view(), name="supplier-detail"),
    path("suppliers/create/", SupplierCreateView.as_view(), name="supplier-create"),
    path("suppliers/<int:pk>/update/", SupplierUpdateView.as_view(), name="supplier-update"),
    path("suppliers/<int:pk>/delete/", SupplierDeleteView.as_view(), name="supplier-delete"),
    path("supplier-contacts/create/", SupplierContactCreateView.as_view(), name="supplier-contact-create"),
    path("supplier-products/create/", SupplierProductCreateView.as_view(), name="supplier-product-create"),
    path("supplier/<int:pk>/purchase-orders/", SupplierPurchaseOrderListView.as_view(), name="supplier-purchaseorders"),
    path("supplier/<int:pk>/products/", SupplierProductListView.as_view(), name="supplier-products"),
    path("purchase-orders/create/", PurchaseOrderCreateView.as_view(), name="purchase-order-create"),
    path("purchase-orders/<int:pk>/", PurchaseOrderDetailView.as_view(), name="purchase-order-detail"),
    path("purchase-orders/receiving/", PurchaseOrderReceivingListView.as_view(), name="purchase-order-receiving-list"),
    path("purchase-orders/<int:pk>/receive/", PurchaseOrderReceiveView.as_view(), name="purchase-order-receive"),
]
