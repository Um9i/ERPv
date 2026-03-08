from django.urls import path

from . import views

app_name = "config"

urlpatterns = [
    path("company/", views.CompanyConfigView.as_view(), name="company-config"),
    path("api/company/", views.CompanyApiView.as_view(), name="company-api"),
    path(
        "paired/", views.PairedInstanceListView.as_view(), name="paired-instance-list"
    ),
    path(
        "paired/create/",
        views.PairedInstanceCreateView.as_view(),
        name="paired-instance-create",
    ),
    path(
        "paired/<int:pk>/delete/",
        views.PairedInstanceDeleteView.as_view(),
        name="paired-instance-delete",
    ),
    path(
        "paired/<int:pk>/complete/",
        views.PairedInstanceCompleteView.as_view(),
        name="paired-instance-complete",
    ),
    path(
        "paired/<int:pk>/import-customer/",
        views.ImportAsCustomerView.as_view(),
        name="import-as-customer",
    ),
    path(
        "paired/<int:pk>/import-supplier/",
        views.ImportAsSupplierView.as_view(),
        name="import-as-supplier",
    ),
]
