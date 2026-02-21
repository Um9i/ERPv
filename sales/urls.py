from django.urls import path
from django.views.generic import TemplateView
from .views import (
    CustomerCreateView,
    CustomerUpdateView,
    CustomerDeleteView,
    CustomerListView,
    CustomerDetailView,
    CustomerContactCreateView,
    CustomerProductCreateView,
    CustomerSalesOrderListView,
    CustomerProductListView,
    CustomerProductIDsView,
    CustomerProductUpdateView,
    CustomerProductDeleteView,
    SalesOrderCreateView,
    SalesOrderDetailView,
    SalesOrderShipListView,
    SalesOrderShipView,
    SalesOrderListView,
    SalesDashboardView,
)

app_name = "sales"

urlpatterns = [
    path("", SalesDashboardView.as_view(), name="sales-dashboard"),
    path("customers/", CustomerListView.as_view(), name="customer-list"),
    path("customers/<int:pk>/", CustomerDetailView.as_view(), name="customer-detail"),
    path("customers/create/", CustomerCreateView.as_view(), name="customer-create"),
    path("customers/<int:pk>/update/", CustomerUpdateView.as_view(), name="customer-update"),
    path("customers/<int:pk>/delete/", CustomerDeleteView.as_view(), name="customer-delete"),
    path("customer-contacts/create/", CustomerContactCreateView.as_view(), name="customer-contact-create"),
    path("customer-products/create/", CustomerProductCreateView.as_view(), name="customer-product-create"),
    path("customer-products/<int:pk>/update/", CustomerProductUpdateView.as_view(), name="customer-product-update"),
    path("customer-products/<int:pk>/delete/", CustomerProductDeleteView.as_view(), name="customer-product-delete"),
    path("customer/<int:pk>/sales-orders/", CustomerSalesOrderListView.as_view(), name="customer-salesorders"),
    path("customer/<int:pk>/products/", CustomerProductListView.as_view(), name="customer-products"),
    path("customer/<int:pk>/product-ids/", CustomerProductIDsView.as_view(), name="customer-product-ids"),
    path("sales-orders/", SalesOrderListView.as_view(), name="sales-order-list"),
    path("sales-orders/create/", SalesOrderCreateView.as_view(), name="sales-order-create"),
    path("sales-orders/<int:pk>/", SalesOrderDetailView.as_view(), name="sales-order-detail"),
    path("sales-orders/shipping/", SalesOrderShipListView.as_view(), name="sales-order-ship-list"),
    path("sales-orders/<int:pk>/ship/", SalesOrderShipView.as_view(), name="sales-order-ship"),
]
