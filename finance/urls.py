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
    path("purchases/", views.PurchaseLedgerArchiveView.as_view(), name="purchase-ledger-archive"),
    path(
        "purchases/<int:year>/<int:month>/",
        views.PurchaseLedgerMonthArchiveView.as_view(),
        name="purchase-ledger-month",
    ),
    path(
        "invoices/<int:year>/<int:month>/",
        views.CustomerInvoiceMonthView.as_view(),
        name="customer-invoices-month",
    ),
    path(
        "invoices/<int:year>/<int:month>/pdf/",
        views.CustomerInvoiceMonthPdfView.as_view(),
        name="customer-invoices-month-pdf",
    ),
    path(
        "supplier-bills/<int:year>/<int:month>/",
        views.SupplierBillingMonthView.as_view(),
        name="supplier-bills-month",
    ),
]
