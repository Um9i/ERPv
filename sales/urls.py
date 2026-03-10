from django.urls import path

from .views import (
    CustomerContactCreateView,
    CustomerContactDeleteView,
    CustomerContactUpdateView,
    CustomerCreateView,
    CustomerDeleteView,
    CustomerDetailView,
    CustomerListView,
    CustomerProductCreateView,
    CustomerProductDeleteView,
    CustomerProductIDsView,
    CustomerProductListView,
    CustomerProductUpdateView,
    CustomerSalesOrderListView,
    CustomerUpdateView,
    PickListCreateView,
    PickListDetailView,
    SalesDashboardView,
    SalesOrderCreateView,
    SalesOrderDetailView,
    SalesOrderInvoiceView,
    SalesOrderListView,
    SalesOrderShipView,
)

app_name = "sales"

urlpatterns = [
    path("", SalesDashboardView.as_view(), name="sales-dashboard"),
    path("customers/", CustomerListView.as_view(), name="customer-list"),
    path("customers/<int:pk>/", CustomerDetailView.as_view(), name="customer-detail"),
    path("customers/create/", CustomerCreateView.as_view(), name="customer-create"),
    path(
        "customers/<int:pk>/update/",
        CustomerUpdateView.as_view(),
        name="customer-update",
    ),
    path(
        "customers/<int:pk>/delete/",
        CustomerDeleteView.as_view(),
        name="customer-delete",
    ),
    path(
        "customer-contacts/create/",
        CustomerContactCreateView.as_view(),
        name="customer-contact-create",
    ),
    path(
        "customer-contacts/<int:pk>/update/",
        CustomerContactUpdateView.as_view(),
        name="customer-contact-update",
    ),
    path(
        "customer-contacts/<int:pk>/delete/",
        CustomerContactDeleteView.as_view(),
        name="customer-contact-delete",
    ),
    path(
        "customer-products/create/",
        CustomerProductCreateView.as_view(),
        name="customer-product-create",
    ),
    path(
        "customer-products/<int:pk>/update/",
        CustomerProductUpdateView.as_view(),
        name="customer-product-update",
    ),
    path(
        "customer-products/<int:pk>/delete/",
        CustomerProductDeleteView.as_view(),
        name="customer-product-delete",
    ),
    path(
        "customer/<int:pk>/sales-orders/",
        CustomerSalesOrderListView.as_view(),
        name="customer-salesorders",
    ),
    path(
        "customer/<int:pk>/products/",
        CustomerProductListView.as_view(),
        name="customer-products",
    ),
    path(
        "customer/<int:pk>/product-ids/",
        CustomerProductIDsView.as_view(),
        name="customer-product-ids",
    ),
    path("sales-orders/", SalesOrderListView.as_view(), name="sales-order-list"),
    path(
        "sales-orders/create/",
        SalesOrderCreateView.as_view(),
        name="sales-order-create",
    ),
    path(
        "sales-orders/<int:pk>/",
        SalesOrderDetailView.as_view(),
        name="sales-order-detail",
    ),
    path(
        "sales-orders/<int:pk>/ship/",
        SalesOrderShipView.as_view(),
        name="sales-order-ship",
    ),
    path(
        "sales-orders/<int:pk>/invoice/",
        SalesOrderInvoiceView.as_view(),
        name="sales-order-invoice",
    ),
    path(
        "sales-orders/<int:pk>/pick-list/",
        PickListCreateView.as_view(),
        name="pick-list-create",
    ),
    path(
        "pick-lists/<int:pk>/",
        PickListDetailView.as_view(),
        name="pick-list-detail",
    ),
]
