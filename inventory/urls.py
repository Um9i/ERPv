from django.urls import path
from django.views.generic import TemplateView
from .views import (
    ProductCreateView,
    ProductUpdateView,
    ProductDeleteView,
    InventoryListView,
    InventoryDetailView,
    InventoryAdjustCreateView,
    InventoryDashboardView,
)

app_name = "inventory"

urlpatterns = [
    path("", InventoryDashboardView.as_view(), name="inventory-dashboard"),
    path("products/create/", ProductCreateView.as_view(), name="product-create"),
    path(
        "products/<int:pk>/update/", ProductUpdateView.as_view(), name="product-update"
    ),
    path(
        "products/<int:pk>/delete/", ProductDeleteView.as_view(), name="product-delete"
    ),
    path("inventories/", InventoryListView.as_view(), name="inventory-list"),
    path(
        "inventories/<int:pk>/", InventoryDetailView.as_view(), name="inventory-detail"
    ),
    path(
        "inventories/<int:pk>/adjust/",
        InventoryAdjustCreateView.as_view(),
        name="inventory-adjust",
    ),
]
