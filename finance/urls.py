from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("", views.FinanceDashboardView.as_view(), name="finance-dashboard"),
    path("sales/", views.SalesLedgerArchiveView.as_view(), name="sales-ledger-archive"),
    path(
        "sales/<int:year>/<int:month>/",
        views.SalesLedgerMonthArchiveView.as_view(),
        name="sales-ledger-month",
    ),
    path(
        "purchases/",
        views.PurchaseLedgerArchiveView.as_view(),
        name="purchase-ledger-archive",
    ),
    path(
        "purchases/<int:year>/<int:month>/",
        views.PurchaseLedgerMonthArchiveView.as_view(),
        name="purchase-ledger-month",
    ),
    path(
        "sales/export/",
        views.SalesLedgerExportView.as_view(),
        name="sales-ledger-export",
    ),
    path(
        "purchases/export/",
        views.PurchaseLedgerExportView.as_view(),
        name="purchase-ledger-export",
    ),
    path(
        "reports/outstanding/",
        views.OutstandingOrdersView.as_view(),
        name="outstanding-orders",
    ),
    path(
        "reports/product-pl/",
        views.ProductPLView.as_view(),
        name="product-pl",
    ),
    path(
        "production/",
        views.ProductionLedgerArchiveView.as_view(),
        name="production-ledger-archive",
    ),
    path(
        "production/<int:year>/<int:month>/",
        views.ProductionLedgerMonthArchiveView.as_view(),
        name="production-ledger-month",
    ),
    path(
        "production/export/",
        views.ProductionLedgerExportView.as_view(),
        name="production-ledger-export",
    ),
]
